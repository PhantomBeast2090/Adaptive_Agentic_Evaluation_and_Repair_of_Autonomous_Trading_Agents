"""R-branch episode wiring for E4-F (E4-owned, calls frozen code only).

This module lives outside the frozen-substrate scan roots
(``evaluation/``, ``environment/``, ``benchmarks/``) precisely so the
R branch can call the frozen harness phase functions without any
frozen file importing anything new. No frozen semantics are modified;
no success, superiority, learning, or self-repair claims are made.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from evaluation.context.driver import DriverPlan
from experiments.harness import lifecycle


def run_r_branch(
    *,
    plan: DriverPlan,
    effective_manifest: Mapping[str, Any],
    config: Any,
    base_dir: str = ".",
) -> Dict[str, Any]:
    """R branch: C0 diagnostic evidence for K2 on W2 (heavy: episodes).

    Uses a fresh C0 agent only. Returns live artefacts plus an
    R-branch fingerprint registry for ``assert_branch_purity``. Never
    touches C1, P observations, or W3.
    """
    if not isinstance(plan, DriverPlan):
        raise TypeError("plan must be a DriverPlan")
    agent = lifecycle.instantiate_agent(config.benchmark_module)
    agent.reset()
    try:
        baseline_w2 = lifecycle.run_baseline(
            agent,
            lifecycle.baseline_config_for(
                config, (plan.w2_start, plan.w2_end),
                f"{plan.experiment_id}-R-W2",
            ),
            base_dir=base_dir,
        )
        diagnostic_state, trace = lifecycle.phase_b(
            config, baseline_w2, effective_manifest, base_dir
        )
    finally:
        del agent
    return {
        "branch": "R",
        "baseline": baseline_w2,
        "diagnostic_state": diagnostic_state,
        "trace": trace,
        "fingerprints": {
            "evaluation": baseline_w2.fingerprint(),
            "diagnosis": diagnostic_state.fingerprint(),
        },
    }


__all__ = ["run_r_branch"]
