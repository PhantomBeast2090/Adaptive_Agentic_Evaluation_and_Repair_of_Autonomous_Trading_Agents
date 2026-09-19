"""Validation tests: three-run structure, held-out discipline, leakage."""

import pytest

from evaluation.diagnostics.repair.validation import (
    VALIDATOR_METHOD,
    VALIDATOR_VERSION,
    ValidationReport,
    ValidationRun,
    run_validation,
)

from ...baseline.stubs import ChurnAgent, HoldAgent
from .fixtures import HoldStub, make_repair_baseline, make_repair_state


def _baseline():
    return make_repair_baseline(
        {
            "turnover": 2.5,
            "cumulative_return": 0.02,
            "invalid_order_count": 0.0,
            "universe_violation_count": 0.0,
            "no_price_count": 0.0,
            "calendar_gate_count": 0.0,
        },
        evaluation_id="B-V",
    )


def test_three_run_structure_and_labels():
    from evaluation.diagnostics.repair.application import (
        apply_repair,
        fingerprint_agent,
    )
    from .test_application import _proposal_for

    baseline = _baseline()
    agent = ChurnAgent()
    proposal = _proposal_for(agent)
    _, _, live = apply_repair(proposal, agent)
    report, artefacts = run_validation(
        validation_id="V-1",
        candidate_id="churn-stub@candidate-x",
        candidate_fingerprint="cfp",
        candidate_agent=live,
        original_agent=agent,
        baseline=baseline,
        heldout_window=("2023-06-01", "2023-06-30"),
        seed=7,
    )
    assert [run.label for run in report.runs] == [
        "candidate_diagnostic",
        "candidate_heldout",
        "original_heldout",
    ]
    assert len(artefacts) == 3
    assert report.method == VALIDATOR_METHOD
    assert report.method_version == VALIDATOR_VERSION
    assert report.fingerprint()


def test_heldout_window_must_be_later_and_disjoint():
    baseline = _baseline()
    agent = HoldAgent()
    with pytest.raises(ValueError):
        run_validation(
            validation_id="V-2",
            candidate_id="c",
            candidate_fingerprint="cfp",
            candidate_agent=agent,
            original_agent=agent,
            baseline=baseline,
            heldout_window=("2023-05-20", "2023-06-10"),
            seed=7,
        )
    with pytest.raises(ValueError):
        run_validation(
            validation_id="V-2",
            candidate_id="c",
            candidate_fingerprint="cfp",
            candidate_agent=agent,
            original_agent=agent,
            baseline=baseline,
            heldout_window=("2023-06-30", "2023-06-01"),
            seed=7,
        )


def test_candidate_receives_only_target_observation():
    from evaluation.contracts.oracle import TargetObservation

    seen_types = []

    class CheckingAgent(HoldAgent):
        def act(self, observation):
            seen_types.append(type(observation).__name__)
            if not isinstance(observation, TargetObservation):
                raise TypeError("validation leaked a non-observation")
            return []

    baseline = _baseline()
    report, _ = run_validation(
        validation_id="V-3",
        candidate_id="c",
        candidate_fingerprint="cfp",
        candidate_agent=CheckingAgent(),
        original_agent=HoldAgent(),
        baseline=baseline,
        heldout_window=("2023-06-01", "2023-06-30"),
        seed=7,
    )
    assert seen_types
    assert set(seen_types) == {"TargetObservation"}
    assert report.run("candidate_diagnostic").metrics["turnover"] == 0.0


def test_validation_run_contract():
    run = ValidationRun(
        label="candidate_diagnostic",
        window=("2024-01-02", "2024-01-02"),
        result_fingerprint="rfp",
        metrics={"turnover": 1.0, "sharpe_per_session": None},
    )
    assert run.value_of("turnover") == 1.0
    assert run.value_of("sharpe_per_session") is None
    assert run.value_of("absent_metric") is None
    assert ValidationRun.from_dict(run.to_dict()) == run
    with pytest.raises(ValueError):
        ValidationRun(
            label="x", window=("2024-01-02", "2024-01-02"),
            result_fingerprint="r", metrics={"m": float("nan")},
        )


def test_report_contract_round_trip():
    report, _ = None, None
    baseline = _baseline()
    from evaluation.diagnostics.repair.application import apply_repair
    from .test_application import _proposal_for
    from ..execution_fixtures import HoldAgent as _Hold

    agent = _Hold()
    _, _, live = apply_repair(_proposal_for(agent), agent)
    report, _ = run_validation(
        validation_id="V-4",
        candidate_id="c",
        candidate_fingerprint="cfp",
        candidate_agent=live,
        original_agent=agent,
        baseline=baseline,
        heldout_window=("2023-06-01", "2023-06-30"),
        seed=7,
    )
    assert ValidationReport.from_dict(report.to_dict()) == report
    with pytest.raises(KeyError):
        report.run("no-such-label")
    with pytest.raises(ValueError):
        ValidationReport.from_dict({**report.to_dict(), "zzz": 1})
