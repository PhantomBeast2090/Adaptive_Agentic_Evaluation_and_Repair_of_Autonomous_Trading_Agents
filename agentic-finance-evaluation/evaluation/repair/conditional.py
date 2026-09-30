"""M-R8 conditional exposure serving scope (additive, strict isolation).

The ONLY experimental modification vs M-R6/M-R7 is the serving scope
wrapper defined here:

    trigger TRUE  -> apply the byte-identical existing repair action;
    trigger FALSE -> reproduce the frozen baseline decision exactly.

Trigger (exact frozen exposure-mechanism condition, no additions):

    exposure_active  <=>  names_held > max_normal_names, with
    max_normal_names = 2 (frozen M-R6/M-R7 detector threshold).

``names_held`` is the count of distinct instruments with quantity > 0 in
the PRE-DECISION portfolio snapshot (own-portfolio accounting only).
No VIX, regime, price, future, outcome, or additional predicate enters
this trigger by construction: the functions below accept only the
portfolio snapshot / adapted row plus the frozen threshold, and the
signature tests pin that no other channel exists.

Parity notes:
- Adapted diagnostic rows (``natural.adapt_records``) carry
  ``names_held`` derived from ``portfolio_before`` positions via the
  same tolerant counting used here.
- Live observations carry the identical portfolio block
  (``run_baseline`` records ``portfolio_before`` as a deep copy of the
  trusted observation portfolio), so the live gate and the adjudication
  flag agree session-by-session.
- Missing/unusable portfolio state fails closed to INACTIVE (preserve
  baseline, never fire).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from benchmarks.observation import as_dict
from evaluation.contracts.agent import AgentIdentity, validate_target_agent
from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.diagnostics.repair.application import snapshot_policy
from evaluation.repair import control_plane
from evaluation.repair.schemas import MemoryEntry

FROZEN_EXPOSURE_MAX_NORMAL_NAMES = 2
FROZEN_EXPOSURE_MECHANISM = "exposure"

CONDITIONAL_METHOD = "conditional-exposure-scope"
CONDITIONAL_VERSION = "v1"


def trigger_spec() -> Dict[str, Any]:
    """Frozen trigger specification (fingerprinted into M-R8 freeze)."""
    return {
        "mechanism": FROZEN_EXPOSURE_MECHANISM,
        "field": "names_held",
        "operator": "gt",
        "threshold": FROZEN_EXPOSURE_MAX_NORMAL_NAMES,
        "method": CONDITIONAL_METHOD,
        "version": CONDITIONAL_VERSION,
    }


def trigger_fingerprint() -> str:
    return fingerprint_of_dict(trigger_spec())


def _count_positions_held(positions: Any) -> int | None:
    """Count distinct instruments with quantity > 0, or None if unusable."""
    if not isinstance(positions, Mapping):
        return None
    count = 0
    seen_any = False
    for _key, slot in positions.items():
        quantity: Any = None
        if isinstance(slot, Mapping):
            quantity = slot.get("quantity", None)
        elif isinstance(slot, (int, float)) and not isinstance(slot, bool):
            quantity = slot
        else:
            continue
        seen_any = True
        try:
            number = float(quantity)
        except (TypeError, ValueError):
            return None
        if number != number or number in (float("inf"), float("-inf")):
            return None
        if number > 0:
            count += 1
    if not seen_any:
        # Empty positions mapping is usable: zero names held.
        return 0
    return count


def exposure_active_from_names_held(names_held: Any) -> bool:
    """Frozen mechanism condition on a raw names_held value.

    Non-integer/unusable inputs fail closed to False (preserve baseline).
    """
    if isinstance(names_held, bool):
        return False
    try:
        held = int(names_held)
    except (TypeError, ValueError):
        return False
    if held != names_held and not (
        isinstance(names_held, float) and float(held) == float(names_held)
    ):
        # Reject non-integral floats conservatively.
        if isinstance(names_held, float) and not names_held.is_integer():
            return False
    return held > FROZEN_EXPOSURE_MAX_NORMAL_NAMES


def exposure_active_from_adapted(row: Mapping[str, Any]) -> bool:
    """Trigger predicate over one PIT-safe adapted diagnostic session row."""
    return exposure_active_from_names_held(row.get("names_held", 0))


def exposure_active_from_payload(payload: Mapping[str, Any]) -> bool:
    """Trigger predicate over one live observation payload.

    Reads ONLY the pre-decision portfolio positions block. Any missing or
    unusable portfolio state fails closed to False.
    """
    portfolio = payload.get("portfolio", None)
    if not isinstance(portfolio, Mapping):
        return False
    held = _count_positions_held(portfolio.get("positions", None))
    if held is None:
        return False
    return held > FROZEN_EXPOSURE_MAX_NORMAL_NAMES


def _base_policy_snapshot(base_agent: Any) -> Mapping[str, Any]:
    nested = getattr(base_agent, "policy_snapshot", None)
    if callable(nested):
        return nested()  # type: ignore[no-any-return]
    return snapshot_policy(base_agent)


def _base_policy_fingerprint(
    base_agent: Any, identity: AgentIdentity
) -> str:
    return fingerprint_of_dict(
        {"identity": identity.to_dict(),
         "policy": _base_policy_snapshot(base_agent)}
    )


def _fingerprint_orders(orders: Sequence[Mapping[str, Any]]) -> str:
    return fingerprint_of_dict(
        {"orders": [dict(order) for order in orders]}
    )


def _fingerprint_payload(payload: Mapping[str, Any]) -> str:
    return fingerprint_of_dict({"observation": dict(payload)})


class ConditionalExposureAgent:
    """Frozen policy + trigger-scoped identical repair action.

    Construction mirrors ``MemoryConditionedAgent`` (exclusive deep copy
    of the base agent, policy fingerprint preservation, replay/shadow
    logs). Behaviour:

    - base policy invoked exactly once per decision;
    - trigger inactive -> return base orders verbatim (bit-equality);
    - trigger active -> apply the entry's byte-identical rule via the
      shared ``control_plane.apply_rule_ops`` (GuardrailedAgent-identical
      semantics), with scope/trigger of the stored spec otherwise
      untouched.

    Strict-isolation scope: exactly ONE active entry per instance (the
    M-R8 per-candidate wrapper). ``cooldown_after_loss`` is refused here
    (absent from the frozen 9-candidate exposure set); its stateful
    arming windows belong to the broad serving path, not to M-R8.
    """

    def __init__(
        self,
        base_agent: Any,
        entries: Sequence[MemoryEntry] = (),
        active_ids: Sequence[str] = (),
        shadow: bool = False,
        wrapper_version: str = "v1-conditional-exposure",
    ) -> None:
        errors = validate_target_agent(base_agent)
        if errors:
            raise TypeError(f"base agent is invalid: {errors}")
        for entry in entries:
            if not isinstance(entry, MemoryEntry):
                raise TypeError(
                    "entries must be MemoryEntry records, got "
                    f"{type(entry).__name__}"
                )
        self._base = copy.deepcopy(base_agent)
        self._base_identity = AgentIdentity(
            base_agent.identity.agent_id, base_agent.identity.version
        )
        self._base_fingerprint = _base_policy_fingerprint(
            self._base, self._base_identity
        )
        self._entries = tuple(entries)
        self._active = tuple(active_ids)
        self._shadow = bool(shadow)
        self._wrapper_version = str(wrapper_version)
        self._replay_log: List[Dict[str, Any]] = []
        self._shadow_log: List[Dict[str, Any]] = []
        self._base_calls = 0
        active_entries = [
            e for e in self._entries if e.entry_id in set(self._active)
        ]
        if len(active_entries) > 1:
            raise ValueError(
                "ConditionalExposureAgent serves exactly one active entry "
                f"(M-R8 strict isolation); got {len(active_entries)}"
            )
        for entry in active_entries:
            if entry.spec.rule_type == "cooldown_after_loss":
                raise ValueError(
                    "cooldown_after_loss is not in the M-R8 exposure "
                    "candidate set; refusing stateful rule on the "
                    "conditional path"
                )
        errors = validate_target_agent(self._base)
        if errors:
            raise TypeError(f"wrapped base copy is invalid: {errors}")

    @property
    def identity(self) -> AgentIdentity:
        digest = fingerprint_of_dict(
            {
                "base": self._base_fingerprint,
                "active": list(self._active),
                "shadow": self._shadow,
                "wrapper_version": self._wrapper_version,
                "trigger": trigger_spec(),
            }
        )
        base = self._base_identity
        return AgentIdentity(base.agent_id, f"{base.version}+c{digest[:8]}")

    @property
    def base_identity(self) -> AgentIdentity:
        return self._base_identity

    @property
    def shadow(self) -> bool:
        return self._shadow

    @property
    def active_ids(self) -> Tuple[str, ...]:
        return self._active

    @property
    def base_calls(self) -> int:
        return self._base_calls

    def base_policy_fingerprint(self) -> str:
        return _base_policy_fingerprint(self._base, self._base_identity)

    def base_policy_snapshot(self) -> Mapping[str, Any]:
        return _base_policy_snapshot(self._base)

    def reset(self) -> None:
        self._base.reset()

    def set_active(
        self, active_ids: Sequence[str], shadow: bool | None = None
    ) -> None:
        self._active = tuple(active_ids)
        if shadow is not None:
            self._shadow = bool(shadow)

    def replay_log(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(dict(record) for record in self._replay_log)

    def shadow_log(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(dict(record) for record in self._shadow_log)

    def act(self, observation: Any) -> Sequence[Mapping[str, Any]]:
        payload = as_dict(observation)
        base_orders = [dict(o) for o in self._base.act(observation)]
        self._base_calls += 1
        payload_fp = _fingerprint_payload(payload)
        base_fp = _fingerprint_orders(base_orders)
        trigger_active = exposure_active_from_payload(payload)
        by_id = {e.entry_id: e for e in self._entries}
        active = [by_id[eid] for eid in self._active if eid in by_id]
        conditioned = [dict(o) for o in base_orders]
        fired_ids: List[str] = []
        if trigger_active and active:
            entry = active[0]
            conditioned = control_plane.apply_rule_ops(
                base_orders, [entry.spec.rule()], observation
            )
            fired_ids.append(entry.entry_id)
        conditioned_fp = _fingerprint_orders(conditioned)
        record = {
            "payload_fingerprint": payload_fp,
            "base_orders_fingerprint": base_fp,
            "trigger_active": bool(trigger_active),
            "trigger": trigger_spec(),
            "fired_ids": list(fired_ids),
            "result_fingerprint": base_fp if self._shadow else conditioned_fp,
            "shadow": self._shadow,
        }
        if self._shadow:
            record["predicted_fingerprint"] = conditioned_fp
            self._shadow_log.append(record)
            return base_orders
        self._replay_log.append(record)
        return conditioned
