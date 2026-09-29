"""MemoryConditionedAgent (M-R0/M-R1, additive).

A wrapper around a frozen target agent that makes retrieved external
memory causally effective WITHOUT modifying the underlying policy:

  base act() -> base orders (frozen policy, called exactly once)
    -> control-plane selection (scope + trigger + conflict resolution)
    -> GuardrailedAgent-identical rule application
    -> final orders + selection provenance

Invariants:
  * The wrapped base copy is exclusively owned; the caller's agent object
    is deep-copied at construction, never referenced afterwards.
  * ``base_policy_fingerprint()`` before/after any number of conditioned
    decisions must equal the pre-wrap fingerprint (policy preservation).
  * SHADOW mode computes what memory WOULD have done, returns base orders
    unchanged, and records the prediction (unverified entries never act).
  * Rollback (deactivate entry) restores base behaviour exactly.
  * Every act() emits a deterministic replay record (observation, fired
    entries, result fingerprints) for audit and deterministic replay.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from benchmarks.observation import as_dict
from evaluation.contracts.agent import AgentIdentity, validate_target_agent
from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.diagnostics.repair.application import (
    fingerprint_agent,
    snapshot_policy,
)
from evaluation.repair import control_plane
from evaluation.repair.schemas import MemoryEntry


def _base_policy_snapshot(base_agent: Any) -> Mapping[str, Any]:
    """Snapshot the INNERMOST policy through adapter stacks.

    The frozen generic snapshot cannot traverse nested owned copies, so
    adapters expose ``policy_snapshot()`` for the inner policy. Plain
    agents snapshot directly. Either way the result is canonicalised by
    the frozen snapshot function — no second mechanism.
    """
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


class MemoryConditionedAgent:
    """Frozen policy + served structured memory = conditioned behaviour."""

    def __init__(
        self,
        base_agent: Any,
        entries: Sequence[MemoryEntry] = (),
        active_ids: Sequence[str] = (),
        shadow: bool = False,
        wrapper_version: str = "v1",
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
        # Cooldown state (M-R5): entry_id -> last suppressed session idx.
        # Session idx counts this wrapper's act() calls since reset, so
        # replay of an identical observation sequence reproduces it.
        self._session_idx = 0
        self._cooldown_until: Dict[str, int] = {}
        errors = validate_target_agent(self._base)
        if errors:  # deepcopy must preserve contract validity
            raise TypeError(f"wrapped base copy is invalid: {errors}")

    @property
    def identity(self) -> AgentIdentity:
        """Wrapper identity: base id, versioned by active memory config."""
        digest = fingerprint_of_dict(
            {
                "base": self._base_fingerprint,
                "active": list(self._active),
                "shadow": self._shadow,
                "wrapper_version": self._wrapper_version,
            }
        )
        base = self._base_identity
        return AgentIdentity(base.agent_id, f"{base.version}+m{digest[:8]}")

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
        """Number of base-policy invocations (audit metadata)."""
        return self._base_calls

    def base_policy_fingerprint(self) -> str:
        """Fingerprint of the owned base copy; must never change."""
        return _base_policy_fingerprint(self._base, self._base_identity)

    def base_policy_snapshot(self) -> Mapping[str, Any]:
        return _base_policy_snapshot(self._base)

    def reset(self) -> None:
        self._base.reset()
        self._session_idx = 0
        self._cooldown_until = {}

    def set_active(
        self, active_ids: Sequence[str], shadow: Optional[bool] = None
    ) -> None:
        """Replace the active set (activation/rollback control)."""
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
        self._session_idx += 1
        idx = self._session_idx
        payload_fp = _fingerprint_payload(payload)
        base_fp = _fingerprint_orders(base_orders)
        selection = control_plane.select(
            self._entries,
            self._active,
            self._base_identity.agent_id,
            payload,
            base_orders,
            payload_fingerprint=payload_fp,
            base_orders_fingerprint=base_fp,
        )
        rules = []
        fired_ids = []
        by_id = {e.entry_id: e for e in self._entries}
        for entry in selection.fired:
            if entry.spec.rule_type == "cooldown_after_loss":
                continue  # handled below via cooldown windows
            rules.append(entry.spec.rule())
            fired_ids.append(entry.entry_id)
        # Stateful cooldown (M-R5): a trigger match arms suppression for
        # the arming session plus the next N sessions. Firing outside an
        # armed window is impossible by construction.
        for eid in self._active:
            entry = by_id.get(eid)
            if entry is None or entry.spec.rule_type != "cooldown_after_loss":
                continue
            params = entry.spec.rule()
            horizon = params.get("sessions", 0)
            if (
                not isinstance(horizon, int)
                or isinstance(horizon, bool)
                or horizon < 0
            ):
                raise ValueError(
                    "cooldown_after_loss requires non-negative integer "
                    f"sessions, got {horizon!r}"
                )
            if control_plane.evaluate_trigger(
                entry.spec.trigger, payload, base_orders
            ):
                self._cooldown_until[eid] = idx + horizon
            if idx <= self._cooldown_until.get(eid, -1):
                rules.append({"type": "block_action", "side": "BUY"})
                fired_ids.append(eid)
        conditioned = control_plane.apply_rule_ops(
            base_orders, rules, observation
        )
        conditioned_fp = _fingerprint_orders(conditioned)
        record = {
            "payload_fingerprint": payload_fp,
            "base_orders_fingerprint": base_fp,
            "fired_ids": list(fired_ids),
            "quarantined": selection.quarantined,
            "result_fingerprint": base_fp if self._shadow else conditioned_fp,
            "shadow": self._shadow,
        }
        if self._shadow:
            record["predicted_fingerprint"] = conditioned_fp
            self._shadow_log.append(record)
            return base_orders
        self._replay_log.append(record)
        return conditioned
