"""Deterministic RepairCompiler (M-R0/M-R1, additive).

Compiles a validated :class:`FailureMechanism` into a :class:`RepairSpec`
using ONLY the approved M-R1 rule vocabulary:

  per_session_order_cap / exposure_cap / hold_all

``max_quantity`` is reserved for M-R3 and is rejected here even if
requested. Anything unmappable yields an explicit UNCOMPILABLE result —
never a forced approximate throttle. (The provider rule-table's DEFAULT
fallback is a separate, deliberately blunter path; the compiler is the
safe path and refuses where the provider would guess.)

Compilation table (deterministic, versioned):
  concentration / exposure  -> exposure_cap {max_names_held: 1}
  volatility / regime /
  Execution                 -> hold_all (REQUIRES a vix regime trigger;
                               without one the mechanism is UNCOMPILABLE,
                               since unscoped suppression is unsafe)
  turnover / accumulation /
  risk / leverage /
  Risk/Sizing               -> per_session_order_cap {max_orders: 1}
  anything else             -> UNCOMPILABLE
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from evaluation.repair.schemas import (
    COMPILER_VERSION,
    FailureMechanism,
    RepairScope,
    RepairSpec,
)

CONCENTRATION_KEYS = ("concentration", "exposure")
VOLATILITY_KEYS = ("volatility", "regime", "execution")
LOSS_CHASING_KEYS = ("loss-chasing", "losschasing", "loss/chasing")
TURNOVER_KEYS = ("turnover", "accumulation", "risk", "leverage")

# hold_all without a regime trigger would suppress the agent on every
# decision including calm markets. The compiler therefore requires the
# mechanism to carry a vix trigger with an upper bound (gt/gte/lt/lte on
# the vix field); otherwise the result is UNCOMPILABLE.
HOLD_ALL_DEFAULT_VIX_FLOOR = 25.0


@dataclass(frozen=True)
class Uncompilable:
    """Explicit refusal: the mechanism has no safe representation."""

    mechanism_id: str
    reason: str
    compiler_version: str = COMPILER_VERSION


def _taxonomy_key(taxonomy: str) -> str:
    return taxonomy.strip().lower().replace("-", "/").replace("_", "/")


def compile(  # noqa: A001 - established domain verb
    mechanism: FailureMechanism,
    spec_id: str,
    priority: int = 0,
) -> RepairSpec | Uncompilable:
    """Compile one validated mechanism to a RepairSpec or UNCOMPILABLE."""
    if not isinstance(mechanism, FailureMechanism):
        raise TypeError(
            f"mechanism must be a FailureMechanism, got "
            f"{type(mechanism).__name__}"
        )
    key = _taxonomy_key(mechanism.taxonomy)
    scope = _compile_scope(mechanism)
    if any(k in key for k in LOSS_CHASING_KEYS):
        # M-R3: bounded quantity ceiling. The cap is pre-registered in
        # the benchmark protocol and carried in scope_hint
        # ("max_quantity_cap"); the compiler never invents it.
        cap = mechanism.scope_hint.get("max_quantity_cap")
        if (
            not isinstance(cap, (int, float))
            or isinstance(cap, bool)
            or cap != cap
            or cap in (float("inf"), float("-inf"))
            or cap <= 0
        ):
            return Uncompilable(
                mechanism_id=mechanism.mechanism_id,
                reason=(
                    "max_quantity requires a pre-registered positive cap "
                    "in scope_hint['max_quantity_cap']"
                ),
            )
        return RepairSpec(
            spec_id=spec_id,
            mechanism_fingerprint=mechanism.fingerprint(),
            rule_type="max_quantity",
            rule_params={"cap": float(cap)},
            scope=scope,
            trigger=tuple(mechanism.trigger_hint),
            priority=priority,
            rationale=(
                f"compiler {COMPILER_VERSION}: {mechanism.taxonomy} -> "
                f"max_quantity{{cap:{float(cap)}}}"
            ),
        )
    if any(k in key for k in CONCENTRATION_KEYS):
        return RepairSpec(
            spec_id=spec_id,
            mechanism_fingerprint=mechanism.fingerprint(),
            rule_type="exposure_cap",
            rule_params={"max_names_held": 1},
            scope=scope,
            trigger=tuple(mechanism.trigger_hint),
            priority=priority,
            rationale=(
                f"compiler {COMPILER_VERSION}: {mechanism.taxonomy} -> "
                "exposure_cap{max_names_held:1}"
            ),
        )
    if any(k in key for k in VOLATILITY_KEYS):
        trigger = tuple(mechanism.trigger_hint)
        if not _has_vix_upper_bound(trigger):
            return Uncompilable(
                mechanism_id=mechanism.mechanism_id,
                reason=(
                    "hold_all requires a vix regime trigger with an upper "
                    "bound; refusing unscoped suppression"
                ),
            )
        return RepairSpec(
            spec_id=spec_id,
            mechanism_fingerprint=mechanism.fingerprint(),
            rule_type="hold_all",
            rule_params={},
            scope=scope,
            trigger=trigger,
            priority=priority,
            rationale=(
                f"compiler {COMPILER_VERSION}: {mechanism.taxonomy} -> "
                "hold_all (regime-triggered)"
            ),
        )
    if any(k in key for k in TURNOVER_KEYS):
        return RepairSpec(
            spec_id=spec_id,
            mechanism_fingerprint=mechanism.fingerprint(),
            rule_type="per_session_order_cap",
            rule_params={"max_orders": 1},
            scope=scope,
            trigger=tuple(mechanism.trigger_hint),
            priority=priority,
            rationale=(
                f"compiler {COMPILER_VERSION}: {mechanism.taxonomy} -> "
                "per_session_order_cap{max_orders:1}"
            ),
        )
    return Uncompilable(
        mechanism_id=mechanism.mechanism_id,
        reason=(
            f"taxonomy {mechanism.taxonomy!r} has no approved M-R1 "
            "representation"
        ),
    )


def _has_vix_upper_bound(
    trigger: Tuple[Tuple[str, str, Any], ...],
) -> bool:
    for field_name, op, _ in trigger:
        if field_name == "vix" and op in ("gt", "gte", "lt", "lte"):
            return True
    return False


def _compile_scope(mechanism: FailureMechanism) -> RepairScope:
    hint = mechanism.scope_hint
    instruments = hint.get("instruments", ())
    actions = hint.get("actions", ())
    band = hint.get("vix_band")
    return RepairScope(
        agent_id=str(hint.get("agent_id", "")),
        instruments=tuple(instruments),
        actions=tuple(actions),
        vix_band=tuple(band) if band is not None else None,  # type: ignore[arg-type]
        date_from=str(hint.get("date_from", "")),
        date_to=str(hint.get("date_to", "")),
    )


# ---------------------------------------------------------------------------
# M-R5 adaptive synthesis: family-driven compilation.
# ---------------------------------------------------------------------------
# A repair FAMILY names an operation shape; PARAMETERS instantiate it.
# Families are eligible per mechanism taxonomy via FAMILIES_FOR_TAXONOMY
# (the mechanism ontology). Builders validate parameters fail-closed;
# anything unmappable yields Uncompilable — never a forced throttle.
# Frozen grids live with the generator (adaptive.py); builders only
# enforce validity. Existing compile() above is untouched.

REPAIR_FAMILIES = (
    "max_quantity",
    "quantity_reduction",
    "cooldown_after_loss",
    "block_action",
    "exposure_cap",
    "per_session_order_cap",
    "hold_all",
    "drawdown_risk_scaler",
)

FAMILIES_FOR_TAXONOMY = {
    "loss_chasing": (
        "max_quantity", "quantity_reduction", "cooldown_after_loss",
        "block_action", "exposure_cap",
    ),
    "overtrading": (
        "per_session_order_cap", "cooldown_after_loss", "hold_all",
        "block_action",
    ),
    "exposure": (
        "exposure_cap", "quantity_reduction", "per_session_order_cap",
        "max_quantity",
    ),
    "volatility": (
        "hold_all", "exposure_cap", "per_session_order_cap",
        "quantity_reduction",
    ),
    "drawdown": (
        "drawdown_risk_scaler", "quantity_reduction", "cooldown_after_loss",
        "hold_all",
    ),
}

# Frozen default drawdown bands [lo, hi, scale]: full size below 2%,
# 75% to 5%, half to 8%, hold beyond. No per-experiment tuning.
DEFAULT_DRAWDOWN_BANDS = (
    (0.02, 0.05, 0.75),
    (0.05, 0.08, 0.5),
    (0.08, 1.0, 0.0),
)


def _positive_number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value != value
        or value in (float("inf"), float("-inf"))
        or value <= 0
    ):
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def _build_max_quantity(mechanism, params, spec_id):
    cap = _positive_number(params.get("cap"), "cap")
    return _spec(
        mechanism, spec_id, "max_quantity", {"cap": cap},
        f"max_quantity{{cap:{cap}}}")


def _build_quantity_reduction(mechanism, params, spec_id):
    fraction = params.get("fraction")
    if (
        not isinstance(fraction, (int, float))
        or isinstance(fraction, bool)
        or not 0.0 < float(fraction) < 1.0
    ):
        raise ValueError("fraction must satisfy 0 < fraction < 1")
    return _spec(
        mechanism, spec_id, "quantity_reduction",
        {"fraction": float(fraction)},
        f"quantity_reduction{{fraction:{float(fraction)}}}")


def _build_cooldown_after_loss(mechanism, params, spec_id):
    sessions = params.get("sessions")
    if (
        not isinstance(sessions, int)
        or isinstance(sessions, bool)
        or sessions < 0
    ):
        raise ValueError("sessions must be a non-negative integer")
    if not tuple(mechanism.trigger_hint):
        raise ValueError(
            "cooldown_after_loss requires a non-empty trigger "
            "(arming condition); refusing always-on suppression")
    return _spec(
        mechanism, spec_id, "cooldown_after_loss",
        {"sessions": sessions},
        f"cooldown_after_loss{{sessions:{sessions}}}")


def _build_block_action(mechanism, params, spec_id):
    side = params.get("side")
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    return _spec(
        mechanism, spec_id, "block_action", {"side": side},
        f"block_action{{side:{side}}}")


def _build_exposure_cap(mechanism, params, spec_id):
    names = params.get("max_names_held")
    if (
        not isinstance(names, int)
        or isinstance(names, bool)
        or names < 1
    ):
        raise ValueError("max_names_held must be a positive integer")
    return _spec(
        mechanism, spec_id, "exposure_cap", {"max_names_held": names},
        f"exposure_cap{{max_names_held:{names}}}")


def _build_order_cap(mechanism, params, spec_id):
    orders = params.get("max_orders")
    if (
        not isinstance(orders, int)
        or isinstance(orders, bool)
        or orders < 0
    ):
        raise ValueError("max_orders must be a non-negative integer")
    return _spec(
        mechanism, spec_id, "per_session_order_cap",
        {"max_orders": orders},
        f"per_session_order_cap{{max_orders:{orders}}}")


def _build_hold_all(mechanism, params, spec_id):
    trigger = tuple(mechanism.trigger_hint)
    if not _has_vix_upper_bound(trigger):
        raise ValueError(
            "hold_all requires a vix regime trigger with an upper bound; "
            "refusing unscoped suppression")
    return _spec(
        mechanism, spec_id, "hold_all", {},
        "hold_all (regime-triggered)")


def _build_drawdown_scaler(mechanism, params, spec_id):
    bands = params.get("bands", DEFAULT_DRAWDOWN_BANDS)
    checked = []
    for band in bands:
        lo, hi, scale = band
        if not 0.0 <= lo < hi <= 1.0:
            raise ValueError(f"invalid drawdown band {band!r}")
        if not 0.0 <= scale <= 1.0:
            raise ValueError(f"drawdown scale out of [0,1]: {band!r}")
        checked.append((float(lo), float(hi), float(scale)))
    return _spec(
        mechanism, spec_id, "drawdown_risk_scaler",
        {"bands": checked},
        f"drawdown_risk_scaler{{bands:{len(checked)}}}")


FAMILY_BUILDERS = {
    "max_quantity": _build_max_quantity,
    "quantity_reduction": _build_quantity_reduction,
    "cooldown_after_loss": _build_cooldown_after_loss,
    "block_action": _build_block_action,
    "exposure_cap": _build_exposure_cap,
    "per_session_order_cap": _build_order_cap,
    "hold_all": _build_hold_all,
    "drawdown_risk_scaler": _build_drawdown_scaler,
}


def _spec(mechanism, spec_id, rule_type, rule_params, rationale):
    scope = _compile_scope(mechanism)
    return RepairSpec(
        spec_id=spec_id,
        mechanism_fingerprint=mechanism.fingerprint(),
        rule_type=rule_type,
        rule_params=dict(rule_params),
        scope=scope,
        trigger=tuple(mechanism.trigger_hint),
        priority=0,
        rationale=f"compiler {COMPILER_VERSION}: {mechanism.taxonomy} -> {rationale}",
    )


def compile_candidate(
    mechanism: FailureMechanism,
    family: str,
    params: Mapping[str, Any],
    spec_id: str,
) -> "RepairSpec | Uncompilable":
    """Compile one (mechanism, family, params) triple or UNCOMPILABLE."""
    if not isinstance(mechanism, FailureMechanism):
        raise TypeError(
            f"mechanism must be a FailureMechanism, got "
            f"{type(mechanism).__name__}"
        )
    if family not in FAMILY_BUILDERS:
        return Uncompilable(
            mechanism_id=mechanism.mechanism_id,
            reason=f"unknown repair family {family!r}",
        )
    eligible = FAMILIES_FOR_TAXONOMY.get(
        mechanism.taxonomy.strip().lower().replace("-", "_").replace(
            "/", "_"),
        ())
    if family not in eligible:
        return Uncompilable(
            mechanism_id=mechanism.mechanism_id,
            reason=(
                f"family {family!r} not eligible for taxonomy "
                f"{mechanism.taxonomy!r}"
            ),
        )
    try:
        return FAMILY_BUILDERS[family](
            mechanism, dict(params or {}), spec_id)
    except (ValueError, TypeError) as exc:
        return Uncompilable(
            mechanism_id=mechanism.mechanism_id,
            reason=f"family {family!r} refused params: {exc}",
        )


# M-R5 family builders are registered in FAMILY_BUILDERS above; the
# ontology FAMILIES_FOR_TAXONOMY maps mechanism taxonomies to eligible
# families. enforce via compile_candidate().
