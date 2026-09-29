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
