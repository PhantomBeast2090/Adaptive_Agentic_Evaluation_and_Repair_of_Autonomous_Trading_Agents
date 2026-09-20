"""RQ3 assembly: named comparators, seal binding, substitution rejection."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.repair.results import RepairDecision, RepairResult
from evaluation.diagnostics.repair.validation import (
    ValidationReport,
    ValidationRun,
)
from experiments.harness.errors import IntegrityFailure
from experiments.harness.lifecycle import phase_e_assemble
from experiments.harness.lineage import SealedBaseline, heldout_scope

from .fixtures import DIAG, HELD, UNIVERSE, make_baseline, make_config


def _pieces():
    config = make_config()
    baseline_nd = make_baseline("E-ND", DIAG, {"turnover": 2.0})
    baseline_nh = make_baseline("E-NH", HELD, {"turnover": 2.5})
    baseline_rd = make_baseline("E-RD", DIAG, {"turnover": 1.0})
    baseline_rh = make_baseline("E-RH", HELD, {"turnover": 1.5})
    scope = heldout_scope(
        heldout_window=HELD,
        universe=dict(UNIVERSE),
        transaction_cost_bps=5.0,
        initial_cash=100000.0,
        strict_pit=True,
        vintage_policy="explicit",
        environment_fingerprint="env-fp-fixture",
    )
    sealed = SealedBaseline.seal(payload=baseline_nh, scope=scope)
    state = DiagnosticState(
        diagnostic_id="D",
        baseline_evaluation_id="E-ND",
        baseline_fingerprint=baseline_nd.fingerprint(),
        agent_identity=AgentIdentity("bench", "1.0"),
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config={},
        budget=EvaluationBudget(None, 10, None, None, None),
    )
    repair = RepairResult(
        repair_id="repair-D-H-turnover",
        proposal_fingerprint="p",
        candidate_id="c",
        candidate_fingerprint="cf",
        validation_fingerprint="vf",
        analysis_fingerprint="af",
        decision=RepairDecision.ACCEPTED,
        reason="fixture",
        method="m",
        method_version="v",
    )
    report = ValidationReport(
        validation_id="V",
        candidate_id="c",
        candidate_fingerprint="cf",
        baseline_evaluation_id="E-ND",
        baseline_fingerprint=baseline_nd.fingerprint(),
        runs=(
            ValidationRun(
                label="candidate_diagnostic",
                window=DIAG,
                result_fingerprint="rfp",
                metrics={"turnover": 1.0},
            ),
        ),
        method="e1-rerun-comparison",
        method_version="v1",
    )
    return (
        config, baseline_nd, sealed, state, repair, report,
        baseline_rd, baseline_rh,
    )


def test_assembly_names_comparators_and_deltas():
    (config, baseline_nd, sealed, state, repair, report,
     baseline_rd, baseline_rh) = _pieces()
    result = phase_e_assemble(
        config=config,
        experiment_id="exp-1",
        baseline_nd=baseline_nd,
        sealed_nh=sealed,
        diagnostic_state=state,
        diagnostic_trace={"completed": [], "invalid_or_failed": []},
        repair_result=repair,
        validation_report=report,
        baseline_rd=baseline_rd,
        baseline_rh=baseline_rh,
    )
    assert result.delta_heldout["baseline_original_heldout"] == (
        sealed.baseline_fingerprint
    )
    assert result.delta_heldout["repaired_heldout"] == (
        baseline_rh.fingerprint()
    )
    assert result.delta_heldout["turnover"]["delta"] == -1.0
    assert result.delta_diagnostic["turnover"]["delta"] == -1.0
    assert result.lineage["baseline_nh_seal"] == sealed.seal_fingerprint
    assert result.fingerprint()


def test_nd_substituted_for_nh_fails_closed():
    (config, baseline_nd, sealed, state, repair, report,
     baseline_rd, baseline_rh) = _pieces()
    baseline_nh = make_baseline("E-ND-CLONE", DIAG, {"turnover": 2.0})
    scope = heldout_scope(
        heldout_window=HELD,
        universe=dict(UNIVERSE),
        transaction_cost_bps=5.0,
        initial_cash=100000.0,
        strict_pit=True,
        vintage_policy="explicit",
        environment_fingerprint="env-fp-fixture",
    )
    wrong_seal = SealedBaseline.seal(payload=baseline_nh, scope=scope)
    with pytest.raises(IntegrityFailure):
        phase_e_assemble(
            config=config,
            experiment_id="exp-1",
            baseline_nd=baseline_nd,
            sealed_nh=wrong_seal,
            diagnostic_state=state,
            diagnostic_trace={},
            repair_result=repair,
            validation_report=report,
            baseline_rd=baseline_rd,
            baseline_rh=baseline_rh,
        )
