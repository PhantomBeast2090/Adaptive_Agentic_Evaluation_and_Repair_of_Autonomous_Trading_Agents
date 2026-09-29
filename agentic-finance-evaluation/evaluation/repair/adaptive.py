"""Adaptive repair synthesis, adjudication, and experiment orchestration.

M-R5: the environment converts a diagnosed FailureMechanism into
multiple candidate RepairSpecs drawn from eligible families, evaluates
each under frozen gates on DIAGNOSTIC data only, adjudicates with a
frozen multi-objective ordering, freezes the winner, and only then
touches held-out data. No human selects the winner; no thresholds move
after results; held-out outcomes can never influence selection.

All randomness-free: candidate ids, grids, ordering, and tie-breaks are
deterministic functions of (protocol, mechanism, diagnostic trace).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from evaluation.repair.compiler import (
    FAMILIES_FOR_TAXONOMY,
    Uncompilable,
    compile_candidate,
)
from evaluation.repair.gate import paired_bootstrap_ci
from evaluation.repair.schemas import FailureMechanism

MECHANISM_TYPES = (
    "loss_chasing",
    "overtrading",
    "exposure",
    "volatility",
    "drawdown",
)

# Frozen parameter grids. max_quantity caps and block_action sides are
# derived from the mechanism/diagnostic trace (documented rules below);
# every other family uses these fixed grids — never searched, never
# tuned per experiment.
FRACTION_GRID = (0.25, 0.5)
COOLDOWN_GRID = (1, 2)
ORDER_CAP_GRID = (1, 2)
NAMES_CAP_GRID = (1, 2)


def _taxonomy_of(failure_type: str) -> str:
    return failure_type


@dataclass(frozen=True)
class MechanismSpec:
    """Data-driven mechanism representation driving family eligibility."""

    mechanism_id: str
    failure_type: str
    trigger_context: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    affected_action: str = "BUY"
    temporal_pattern: str = ""
    severity: float = 0.0
    frequency: float = 0.0
    support: int = 0
    evidence_refs: Tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.failure_type not in MECHANISM_TYPES:
            raise ValueError(
                f"unknown failure_type {self.failure_type!r}; "
                f"expected one of {list(MECHANISM_TYPES)}"
            )
        if self.affected_action not in ("BUY", "SELL"):
            raise ValueError("affected_action must be BUY or SELL")
        if not isinstance(self.support, int) or self.support < 0:
            raise ValueError("support must be a non-negative integer")


def _prev_negative(sessions: List[Dict[str, Any]], index: int) -> bool:
    if index <= 0:
        return False
    try:
        return float(sessions[index - 1].get("reward", 0.0)) < 0.0
    except (TypeError, ValueError):
        return False


def detect_loss_chasing(
    sessions: List[Dict[str, Any]],
    normal_qty: float,
    min_support: int,
    mechanism_id: str,
) -> Optional[MechanismSpec]:
    """Post-loss quantity escalation above the normal size."""
    hits = [
        i for i, s in enumerate(sessions)
        if _prev_negative(sessions, i)
        and float(s.get("buy_quantity", 0.0) or 0.0) > normal_qty
    ]
    if len(hits) < min_support:
        return None
    peak = max(float(sessions[i].get("buy_quantity", 0.0)) for i in hits)
    return MechanismSpec(
        mechanism_id=mechanism_id,
        failure_type="loss_chasing",
        trigger_context={"post_loss": True, "normal_quantity": normal_qty},
        affected_action="BUY",
        temporal_pattern="post-loss escalation",
        severity=peak / normal_qty if normal_qty > 0 else 0.0,
        frequency=len(hits) / len(sessions) if sessions else 0.0,
        support=len(hits),
        evidence_refs=(f"escalation_sessions:{len(hits)}",),
        provenance={"detector": "detect_loss_chasing"},
    )


def detect_overtrading(
    sessions: List[Dict[str, Any]],
    max_normal_orders: int,
    min_support: int,
    mechanism_id: str,
) -> Optional[MechanismSpec]:
    """Sustained per-session order counts above the normal ceiling."""
    hits = [
        i for i, s in enumerate(sessions)
        if int(s.get("order_count", 0) or 0) > max_normal_orders
    ]
    if len(hits) < min_support:
        return None
    peak = max(int(sessions[i].get("order_count", 0)) for i in hits)
    return MechanismSpec(
        mechanism_id=mechanism_id,
        failure_type="overtrading",
        trigger_context={"max_normal_orders": max_normal_orders},
        affected_action="BUY",
        temporal_pattern="sustained order burst",
        severity=peak / max(max_normal_orders, 1),
        frequency=len(hits) / len(sessions) if sessions else 0.0,
        support=len(hits),
        evidence_refs=(f"burst_sessions:{len(hits)}",),
        provenance={"detector": "detect_overtrading"},
    )


def detect_exposure(
    sessions: List[Dict[str, Any]],
    max_normal_names: int,
    min_support: int,
    mechanism_id: str,
) -> Optional[MechanismSpec]:
    """Breadth accumulation beyond the normal name count."""
    hits = [
        i for i, s in enumerate(sessions)
        if int(s.get("names_held", 0) or 0) > max_normal_names
    ]
    if len(hits) < min_support:
        return None
    peak = max(int(sessions[i].get("names_held", 0)) for i in hits)
    return MechanismSpec(
        mechanism_id=mechanism_id,
        failure_type="exposure",
        trigger_context={"max_normal_names": max_normal_names},
        affected_action="BUY",
        temporal_pattern="breadth accumulation",
        severity=peak / max(max_normal_names, 1),
        frequency=len(hits) / len(sessions) if sessions else 0.0,
        support=len(hits),
        evidence_refs=(f"breadth_sessions:{len(hits)}",),
        provenance={"detector": "detect_exposure"},
    )


def detect_volatility_blindness(
    sessions: List[Dict[str, Any]],
    vix_series: Sequence[float],
    vix_high: float,
    min_support: int,
    mechanism_id: str,
) -> Optional[MechanismSpec]:
    """BUY accumulation during high-VIX sessions without any reduction."""
    hits = [
        i for i, s in enumerate(sessions)
        if i < len(vix_series) and vix_series[i] > vix_high
        and float(s.get("buy_quantity", 0.0) or 0.0) > 0
    ]
    if len(hits) < min_support:
        return None
    return MechanismSpec(
        mechanism_id=mechanism_id,
        failure_type="volatility",
        trigger_context={"vix_high": vix_high},
        affected_action="BUY",
        temporal_pattern="high-VIX accumulation",
        severity=len(hits) / len(sessions) if sessions else 0.0,
        frequency=len(hits) / len(sessions) if sessions else 0.0,
        support=len(hits),
        evidence_refs=(f"high_vix_buys:{len(hits)}",),
        provenance={"detector": "detect_volatility_blindness"},
    )


def detect_drawdown_escalation(
    sessions: List[Dict[str, Any]],
    drawdown_threshold: float,
    normal_qty: float,
    min_support: int,
    mechanism_id: str,
) -> Optional[MechanismSpec]:
    """Quantity escalation while in drawdown beyond threshold."""
    hits = [
        i for i, s in enumerate(sessions)
        if float(s.get("drawdown", 0.0) or 0.0) > drawdown_threshold
        and float(s.get("buy_quantity", 0.0) or 0.0) > normal_qty
    ]
    if len(hits) < min_support:
        return None
    return MechanismSpec(
        mechanism_id=mechanism_id,
        failure_type="drawdown",
        trigger_context={"drawdown_threshold": drawdown_threshold,
                         "normal_quantity": normal_qty},
        affected_action="BUY",
        temporal_pattern="drawdown escalation",
        severity=len(hits) / len(sessions) if sessions else 0.0,
        frequency=len(hits) / len(sessions) if sessions else 0.0,
        support=len(hits),
        evidence_refs=(f"drawdown_escalations:{len(hits)}",),
        provenance={"detector": "detect_drawdown_escalation"},
    )


DETECTORS: Dict[str, Callable[..., Optional[MechanismSpec]]] = {
    "loss_chasing": detect_loss_chasing,
    "overtrading": detect_overtrading,
    "exposure": detect_exposure,
    "volatility": detect_volatility_blindness,
    "drawdown": detect_drawdown_escalation,
}


def eligible_families(failure_type: str) -> Tuple[str, ...]:
    """Ontology lookup: mechanism taxonomy -> eligible repair families."""
    key = failure_type.strip().lower().replace("-", "_").replace("/", "_")
    return FAMILIES_FOR_TAXONOMY.get(key, ())


@dataclass(frozen=True)
class GeneratedCandidate:
    candidate_id: str
    family: str
    params: Mapping[str, Any]
    spec_fingerprint: str = ""


def _distinct_quantities(sessions: List[Dict[str, Any]]) -> List[float]:
    values = sorted({
        float(s.get("buy_quantity", 0.0) or 0.0)
        for s in sessions
        if float(s.get("buy_quantity", 0.0) or 0.0) > 0
    })
    return values


def generate_candidates(
    mechanism: MechanismSpec,
    diagnostic_sessions: List[Dict[str, Any]],
    experiment_id: str,
    normal_quantity: float = 5.0,
) -> List[GeneratedCandidate]:
    """Frozen candidate synthesis from diagnostic data ONLY.

    - max_quantity caps: three smallest distinct observed BUY quantities
      (deterministic rule; never the escalation tail).
    - block_action side: the mechanism's affected action.
    - every other family: frozen grids above.
    Family order follows the ontology tuple; params sorted; ids
    deterministic. Held-out data must never reach this function
    (enforced by signature: no held-out argument exists).
    """
    families = eligible_families(mechanism.failure_type)
    quantities = _distinct_quantities(diagnostic_sessions)
    out: List[GeneratedCandidate] = []
    for family in families:
        grids: List[Dict[str, Any]] = []
        if family == "max_quantity":
            grids = [{"cap": q} for q in quantities[:3]]
        elif family == "quantity_reduction":
            grids = [{"fraction": f} for f in FRACTION_GRID]
        elif family == "cooldown_after_loss":
            grids = [{"sessions": n} for n in COOLDOWN_GRID]
        elif family == "block_action":
            # Both the affected side and its opposite: the opposite-side
            # variant is a documented negative control — it cannot address
            # the mechanism, so the primary gate must reject it even if
            # economics shift. Never remove this without a protocol bump.
            opposite = "SELL" if mechanism.affected_action == "BUY" else "BUY"
            grids = [{"side": mechanism.affected_action},
                     {"side": opposite}]
        elif family == "exposure_cap":
            grids = [{"max_names_held": n} for n in NAMES_CAP_GRID]
        elif family == "per_session_order_cap":
            grids = [{"max_orders": n} for n in ORDER_CAP_GRID]
        elif family == "hold_all":
            grids = [{}]
        elif family == "drawdown_risk_scaler":
            grids = [{}]
        for params in grids:
            key = ",".join(
                f"{k}={params[k]}" for k in sorted(params))
            out.append(GeneratedCandidate(
                candidate_id=f"{experiment_id}-C-{family}"
                + (f"-{key}" if key else ""),
                family=family,
                params=dict(params),
            ))
    _ = normal_quantity
    return out


@dataclass
class CandidateEvaluation:
    candidate_id: str
    family: str
    params: Mapping[str, Any]
    spec_fingerprint: str
    target_reduction: float  # paired mean diff, improvement-negative
    ci_lower: float
    ci_upper: float
    support: int
    fires: int
    suppression_rate: float
    normal_preserved: bool
    final_value: float
    base_final_value: float
    drawdown: float
    base_drawdown: float
    inactivity: float
    base_inactivity: float
    policy_ok: bool
    validity_ok: bool


@dataclass(frozen=True)
class Adjudication:
    ranked_ids: Tuple[str, ...]
    selected_id: str
    reasons: Mapping[str, Any]
    rejected: Tuple[str, ...] = ()


def adjudicate_candidates(
    evaluations: Sequence[CandidateEvaluation],
    min_support: int,
    tolerance_value: float,
    tolerance_drawdown: float,
) -> Adjudication:
    """Frozen multi-objective adjudication (no tuning possible).

    Must-pass gates (failure -> REJECT with reason):
      policy unchanged, behaviour changed (fires>0), support, CI
      excludes null in the improvement direction, inactivity guard,
      economics within tolerances.
    Ordering among survivors: largest target reduction, then highest
    final value, then lowest intervention (suppression rate), then
    lexicographic candidate id (deterministic tie-break).
    """
    survivors: List[CandidateEvaluation] = []
    rejected: List[str] = []
    reasons: Dict[str, Any] = {}
    for ev in evaluations:
        why: List[str] = []
        if not ev.policy_ok:
            why.append("policy fingerprint changed")
        if ev.fires <= 0:
            why.append("repair never fired")
        if ev.support < min_support:
            why.append(
                f"support {ev.support} below minimum {min_support}")
        if not ev.ci_upper < 0:
            why.append("bootstrap CI does not exclude null")
        if not ev.normal_preserved:
            why.append("normal-session behaviour altered")
        if not ev.validity_ok:
            why.append("validity regression")
        if ev.inactivity >= 1.0:
            why.append("full inactivity")
        if ev.final_value < ev.base_final_value * (1.0 - tolerance_value):
            why.append("economic regression beyond tolerance")
        if ev.drawdown > ev.base_drawdown + tolerance_drawdown:
            why.append("drawdown regression beyond tolerance")
        if why:
            rejected.append(ev.candidate_id)
            reasons[ev.candidate_id] = {"rejected": why}
        else:
            survivors.append(ev)
    ranked = sorted(
        survivors,
        key=lambda ev: (ev.target_reduction, -ev.final_value,
                        ev.suppression_rate, ev.candidate_id),
    )
    if ranked:
        selected = ranked[0]
        reasons[selected.candidate_id] = {
            "selected": True,
            "target_reduction": selected.target_reduction,
            "final_value": selected.final_value,
            "suppression_rate": selected.suppression_rate,
        }
        selected_id = selected.candidate_id
    else:
        selected_id = ""
        reasons["selection"] = "NO ADMISSIBLE REPAIR"
    return Adjudication(
        ranked_ids=tuple(ev.candidate_id for ev in ranked),
        selected_id=selected_id,
        reasons=dict(reasons),
        rejected=tuple(rejected),
    )
