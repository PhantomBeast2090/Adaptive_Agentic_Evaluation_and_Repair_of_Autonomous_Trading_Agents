"""Deterministic memory control plane (M-R0/M-R1, additive).

Serves structured :class:`MemoryEntry` records to the wrapper agent:

  retrieve (exact agent_id from the serving list)
    -> scope filtering (agent/instruments/actions/vix-band/dates)
    -> deterministic trigger evaluation (ANDed clauses)
    -> conflict resolution (specificity > priority > version > sequence;
       full tie with differing rules -> QUARANTINE, apply neither)
    -> rule application (GuardrailedAgent-identical semantics)

The serving list is a versioned materialization of admitted knowledge, NOT
a second store: every served entry must reference an ADMITTED store
context (see :func:`verify_admission`), and the append-only MemoryStore
remains the system of record. Rollback is append-only deactivation of the
active set; history is preserved in the audit chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from benchmarks.observation import (
    read_cash,
    read_indicator_close,
    read_positions,
)
from evaluation.diagnostics.repair.application import GuardrailedAgent
from evaluation.repair.schemas import MemoryEntry, RepairScope

VIX_SLOT = "indiavix"


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def resolve_trigger_field(
    field_name: str,
    payload: Mapping[str, Any],
    base_orders: Sequence[Mapping[str, Any]],
) -> Any:
    """Resolve one trigger field to a comparable value (None if unusable)."""
    if field_name == "vix":
        return read_indicator_close(payload, VIX_SLOT)
    if field_name == "cash":
        return read_cash(payload)
    if field_name == "exposure":
        portfolio = payload.get("portfolio", {})
        if not isinstance(portfolio, Mapping):
            return None
        return _finite_number(portfolio.get("exposure"))
    if field_name == "drawdown":
        # Position-underwater fraction from own-portfolio accounting only:
        # max(0, -unrealized_pnl / total_equity). Stateless, PIT-safe
        # (no price history, no future data). Unusable inputs fail closed.
        portfolio = payload.get("portfolio", {})
        if not isinstance(portfolio, Mapping):
            return None
        unrealized = _finite_number(portfolio.get("unrealized_pnl"))
        equity = _finite_number(portfolio.get("total_equity"))
        if unrealized is None or equity is None or equity <= 0:
            return None
        return max(0.0, -unrealized / equity)
    if field_name == "buy_present":
        return any(o.get("side") == "BUY" for o in base_orders)
    if field_name == "sell_present":
        return any(o.get("side") == "SELL" for o in base_orders)
    if field_name == "date":
        timestamp = payload.get("decision_timestamp")
        return timestamp if isinstance(timestamp, str) else None
    raise ValueError(f"unknown trigger field {field_name!r}")


def evaluate_trigger(
    trigger: Sequence[Tuple[str, str, Any]],
    payload: Mapping[str, Any],
    base_orders: Sequence[Mapping[str, Any]],
) -> bool:
    """AND over clauses; any unusable field value fails the clause."""
    for field_name, op, expected in trigger:
        value = resolve_trigger_field(field_name, payload, base_orders)
        if value is None:
            return False
        if op == "eq":
            ok = value == expected
        elif op == "ne":
            ok = value != expected
        elif op == "gt":
            ok = value > expected
        elif op == "gte":
            ok = value >= expected
        elif op == "lt":
            ok = value < expected
        elif op == "lte":
            ok = value <= expected
        elif op == "in":
            ok = value in expected
        elif op == "not_in":
            ok = value not in expected
        else:
            raise ValueError(f"unknown trigger operator {op!r}")
        if not ok:
            return False
    return True


def _order_instruments(base_orders: Sequence[Mapping[str, Any]]) -> List[str]:
    names = []
    for order in base_orders:
        instrument = order.get("instrument")
        asset_id = order.get("asset_id")
        if isinstance(instrument, str):
            names.append(instrument)
            if isinstance(asset_id, str):
                names.append(f"{asset_id}:{instrument}")
    return names


def scope_matches(
    scope: RepairScope,
    agent_id: str,
    payload: Mapping[str, Any],
    base_orders: Sequence[Mapping[str, Any]],
) -> bool:
    """True iff every constrained scope axis matches the decision context."""
    if scope.agent_id and scope.agent_id != agent_id:
        return False
    if scope.instruments:
        names = _order_instruments(base_orders)
        if not any(name in scope.instruments for name in names):
            # An entry scoped to instruments the agent is not trading
            # must not fire (scope safety), including on empty orders.
            return False
    if scope.actions:
        sides = {o.get("side") for o in base_orders}
        if not any(side in scope.actions for side in sides):
            return False
    if scope.vix_band is not None:
        vix = read_indicator_close(payload, VIX_SLOT)
        lo, hi = scope.vix_band
        if vix is None or not lo <= vix:
            return False
        if hi is not None and not vix < hi:
            return False
    timestamp = payload.get("decision_timestamp")
    if scope.date_from and (
        not isinstance(timestamp, str) or timestamp < scope.date_from
    ):
        return False
    if scope.date_to and (
        not isinstance(timestamp, str) or timestamp > scope.date_to
    ):
        return False
    return True


def apply_rule_ops(
    base_orders: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    observation: Any,
) -> List[Dict[str, Any]]:
    """Apply rule ops with GuardrailedAgent-identical semantics.

    Enforcement is reused, not reimplemented: ``exposure_cap`` delegates
    to ``GuardrailedAgent._apply_exposure_cap``; ``hold_all`` and
    ``per_session_order_cap`` are the same two operations
    (pinned by conformance test vs ``GuardrailedAgent.act``). M-R5
    extension ops (``quantity_reduction``, ``block_action``,
    ``drawdown_risk_scaler``) live ONLY on this serving path — the
    frozen ``GuardrailedAgent`` vocabulary is untouched. A dedicated
    function (rather than an ephemeral GuardrailedAgent) is required
    because the wrapper must call the base policy exactly once per
    decision — re-invoking ``act`` would corrupt stateful policies
    (e.g. LossChasing loss counters).
    """
    orders = [dict(o) for o in base_orders]
    for rule in rules:
        kind = rule.get("type")
        if kind == "hold_all":
            return []
        if kind == "per_session_order_cap":
            orders = orders[: rule["max_orders"]]
        elif kind == "exposure_cap":
            orders = list(
                GuardrailedAgent._apply_exposure_cap(
                    orders, observation, rule
                )
            )
        elif kind == "max_quantity":
            orders = list(
                GuardrailedAgent._apply_max_quantity(orders, rule)
            )
        elif kind == "quantity_reduction":
            orders = _apply_quantity_reduction(orders, rule)
        elif kind == "block_action":
            side = rule.get("side")
            if side not in ("BUY", "SELL"):
                raise ValueError(
                    f"block_action requires side BUY/SELL, got {side!r}"
                )
            orders = [
                order for order in orders
                if order.get("side") != side
            ]
        elif kind == "drawdown_risk_scaler":
            orders = _apply_drawdown_risk_scaler(
                orders, observation, rule
            )
        else:
            raise ValueError(
                f"unsupported guardrail rule type {kind!r}: refusing "
                "to degrade into an undeclared no-op"
            )
    return orders


def _apply_quantity_reduction(
    orders: Sequence[Mapping[str, Any]],
    rule: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Scale every order quantity by a fixed fraction (M-R5).

    ``fraction`` must satisfy 0 < fraction < 1 (validated by the
    compiler/admission path; re-checked here fail-closed). Orders scaled
    to non-positive quantity are dropped. Deterministic and stateless.
    """
    fraction = rule.get("fraction")
    if (
        not isinstance(fraction, (int, float))
        or isinstance(fraction, bool)
        or not 0.0 < float(fraction) < 1.0
    ):
        raise ValueError(
            "quantity_reduction requires 0 < fraction < 1, "
            f"got {fraction!r}"
        )
    scaled = []
    for order in orders:
        reduced = dict(order)
        try:
            quantity = float(reduced.get("quantity", 0.0))
        except (TypeError, ValueError):
            scaled.append(order)
            continue
        reduced["quantity"] = quantity * float(fraction)
        if reduced["quantity"] > 0:
            scaled.append(reduced)
    return scaled


def _apply_drawdown_risk_scaler(
    orders: Sequence[Mapping[str, Any]],
    observation: Any,
    rule: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Scale quantities by explicit drawdown band (M-R5).

    ``bands`` is a frozen ordered list of [lo, hi, scale] triples over
    the own-portfolio drawdown fraction; the first matching band wins,
    non-matching drawdown passes through unchanged. Deterministic,
    stateless, PIT-safe (own portfolio only).
    """
    bands = rule.get("bands")
    if not isinstance(bands, (list, tuple)) or not bands:
        raise ValueError("drawdown_risk_scaler requires a non-empty bands list")
    try:
        payload = (
            observation.to_dict()
            if hasattr(observation, "to_dict")
            else dict(observation)
        )
        portfolio = payload.get("portfolio", {})
        unrealized = _finite_number(portfolio.get("unrealized_pnl"))
        equity = _finite_number(portfolio.get("total_equity"))
        drawdown = (
            max(0.0, -unrealized / equity)
            if unrealized is not None and equity
            else 0.0
        )
    except (TypeError, ValueError, AttributeError):
        return [dict(o) for o in orders]
    scale = 1.0
    for band in bands:
        lo, hi, candidate = band
        if lo <= drawdown < hi:
            scale = float(candidate)
            break
    if not 0.0 <= scale <= 1.0:
        raise ValueError(
            f"drawdown_risk_scaler scale out of [0,1]: {scale!r}"
        )
    if scale == 1.0:
        return [dict(o) for o in orders]
    scaled = []
    for order in orders:
        reduced = dict(order)
        try:
            quantity = float(reduced.get("quantity", 0.0))
        except (TypeError, ValueError):
            scaled.append(order)
            continue
        reduced["quantity"] = quantity * scale
        if reduced["quantity"] > 0:
            scaled.append(reduced)
    return scaled


@dataclass(frozen=True)
class SelectionRecord:
    """Provenance for one control-plane selection."""

    agent_id: str
    considered_ids: Tuple[str, ...] = ()
    fired_ids: Tuple[str, ...] = ()
    quarantined: bool = False
    quarantine_reason: str = ""
    payload_fingerprint: str = ""
    base_orders_fingerprint: str = ""


@dataclass(frozen=True)
class Selection:
    fired: Tuple[MemoryEntry, ...] = ()
    quarantined: bool = False
    quarantine_reason: str = ""
    record: SelectionRecord = field(
        default_factory=lambda: SelectionRecord(agent_id="")
    )


def _resolution_key(entry: MemoryEntry) -> Tuple[int, int, str, int]:
    return (
        entry.spec.scope.specificity() + len(entry.spec.trigger),
        entry.priority,
        entry.version,
        entry.sequence,
    )


def select(
    entries: Sequence[MemoryEntry],
    active_ids: Sequence[str],
    agent_id: str,
    payload: Mapping[str, Any],
    base_orders: Sequence[Mapping[str, Any]],
    payload_fingerprint: str = "",
    base_orders_fingerprint: str = "",
) -> Selection:
    """Deterministic selection over the active serving list."""
    active = {e.entry_id: e for e in entries if e.entry_id in set(active_ids)}
    considered = tuple(sorted(active))
    matched = [
        entry
        for entry in active.values()
        if entry.agent_id == agent_id
        and scope_matches(entry.spec.scope, agent_id, payload, base_orders)
        and evaluate_trigger(entry.spec.trigger, payload, base_orders)
    ]
    # Deduplicate identical rules; group distinct ones for resolution.
    by_rule: Dict[str, List[MemoryEntry]] = {}
    for entry in matched:
        by_rule.setdefault(_rule_key(entry), []).append(entry)
    record_base = {
        "agent_id": agent_id,
        "considered_ids": considered,
        "payload_fingerprint": payload_fingerprint,
        "base_orders_fingerprint": base_orders_fingerprint,
    }
    if not by_rule:
        return Selection(
            fired=(),
            record=SelectionRecord(**record_base, fired_ids=()),
        )
    if len(by_rule) == 1:
        winners = next(iter(by_rule.values()))
        return Selection(
            fired=tuple(sorted(winners, key=lambda e: e.entry_id)),
            record=SelectionRecord(
                **record_base,
                fired_ids=tuple(sorted(e.entry_id for e in winners)),
            ),
        )
    ranked = sorted(
        (key, group) for key, group in by_rule.items()
    )
    best: List[MemoryEntry] = []
    best_key: Optional[Tuple[int, int, str, int]] = None
    for _, group in ranked:
        key = max(_resolution_key(e) for e in group)
        if best_key is None or key > best_key:
            best_key = key
            best = list(group)
        elif key == best_key:
            best.extend(group)
    # Full tie across differing rules -> quarantine: apply neither.
    distinct_rules = {k for k, _ in ranked
                      if max(_resolution_key(e) for e in _) == best_key}
    if len(distinct_rules) > 1:
        winner_ids: Tuple[str, ...] = ()
        # Tie-break check: identical resolution keys on differing rules.
        return Selection(
            fired=(),
            quarantined=True,
            quarantine_reason=(
                "indistinguishable conflicting repairs: "
                f"{sorted(distinct_rules)}"
            ),
            record=SelectionRecord(**record_base, fired_ids=winner_ids,
                                   quarantined=True,
                                   quarantine_reason=(
                                       "indistinguishable conflicting "
                                       "repairs"
                                   )),
        )
    winners = [e for e in best if _resolution_key(e) == best_key]
    return Selection(
        fired=tuple(sorted(winners, key=lambda e: e.entry_id)),
        record=SelectionRecord(
            **record_base,
            fired_ids=tuple(sorted(e.entry_id for e in winners)),
        ),
    )


def _rule_key(entry: MemoryEntry) -> str:
    from evaluation.contracts.fingerprints import fingerprint_of_dict

    return fingerprint_of_dict(entry.spec.rule())


def activate(
    active_ids: Sequence[str], entry_id: str
) -> Tuple[str, ...]:
    """Append-only activation; returns the new active set."""
    if entry_id in set(active_ids):
        return tuple(active_ids)
    return tuple(active_ids) + (entry_id,)


def deactivate(
    active_ids: Sequence[str], entry_id: str
) -> Tuple[str, ...]:
    """Append-only deactivation (rollback); history preserved by caller."""
    return tuple(e for e in active_ids if e != entry_id)


def verify_admission(store: Any, entry: MemoryEntry) -> bool:
    """Check the entry references an ADMITTED store context.

    Requires ``entry.provenance["candidate_fingerprint"]`` to match a
    StoredEntry whose context is ADMITTED. Entries built for unit tests
    carry synthetic provenance and must bypass via explicit test-only
    paths — production serving always verifies.
    """
    from evaluation.context.learned import ContextStatus

    wanted = entry.provenance.get("candidate_fingerprint", "")
    for stored in store.entries:
        context = stored.context
        if (
            getattr(stored, "candidate_fingerprint", "")
            == wanted
            and wanted
            and context.status is ContextStatus.ADMITTED
        ):
            return True
    return False
