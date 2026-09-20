"""Focused E2-F budget-accounting tests: persistent consumption invariants.

Repair budget: one admitted run_repair = 1 unit consumed BEFORE provider /
application / validation work; all outcomes consume; no rollback; refusal
appends nothing and invokes nothing. Validation budget: one complete
validation = 3 units; <3 remaining refuses before execution; partial failure
records invoked-run count N in {1,2,3} with no rollback.

Cheap (failure-path, zero-episode) tests run first; env-heavy tests last.
Return shapes are asserted unchanged (4-tuple run_repair, 2-tuple
run_validation) throughout.
"""

import pytest

from evaluation.contracts.budget import EvaluationBudget
from evaluation.diagnostics.repair.accounting import (
    ADMISSION_RECORD_KIND,
    COMPLETED_OUTCOME,
    PARTIAL_OUTCOME,
    RepairAdmission,
    RepairBudgetLedger,
    ValidationConsumption,
    admission_marker_id,
)
from evaluation.diagnostics.repair.provider import DeterministicRuleProvider
from evaluation.diagnostics.repair.results import RepairDecision, run_repair
from evaluation.diagnostics.repair.validation import ValidationPartialFailure

from ..execution_fixtures import ExplodingAgent, HoldAgent
from .fixtures import make_repair_baseline, make_repair_state
from .test_integration import TripleAgent

_HELDOUT = ("2023-06-01", "2023-06-30")
_METRICS = {
    "turnover": 2.5,
    "cumulative_return": 0.02,
    "invalid_order_count": 0.0,
    "universe_violation_count": 0.0,
    "no_price_count": 0.0,
    "calendar_gate_count": 0.0,
}
_ACCEPT_METRICS = {
    "turnover": 5.0,
    "cumulative_return": -0.5,
    "inactivity_rate": 0.0,
    "invalid_order_count": 0.0,
    "universe_violation_count": 0.0,
    "no_price_count": 0.0,
    "calendar_gate_count": 0.0,
}


class SpyBrokenProvider:
    """Counts propose calls, then raises (zero-episode failure path)."""

    deterministic = True
    method = "spy-broken"
    version = "v1"

    def __init__(self):
        self.calls = 0

    def propose(self, **kwargs):
        self.calls += 1
        raise RuntimeError("spy provider blew up")


class SpyDelegateProvider:
    """Counts propose calls, then delegates to the deterministic provider."""

    deterministic = True
    method = "spy-delegate"
    version = "v1"

    def __init__(self):
        self.calls = 0
        self._inner = DeterministicRuleProvider()

    def propose(self, **kwargs):
        self.calls += 1
        return self._inner.propose(**kwargs)


def _ledger_of(state):
    return RepairBudgetLedger.from_evaluation_state(state.evaluation_state)


def _run(state, baseline, agent, provider, **overrides):
    params = {
        "diagnostic_state": state,
        "baseline": baseline,
        "original_agent": agent,
        "hypothesis_id": "H-1",
        "heldout_window": _HELDOUT,
        "seed": 7,
        "provider": provider,
    }
    params.update(overrides)
    return run_repair(**params)


# -- ledger unit contract (zero episodes) -------------------------------

def test_ledger_records_reject_bad_values():
    with pytest.raises(ValueError):
        RepairAdmission(
            repair_id="r", diagnostic_id="d", hypothesis_id="h",
            record_kind="not-admission",
        )
    with pytest.raises(ValueError):
        ValidationConsumption(repair_id="r", runs_consumed=0)
    with pytest.raises(ValueError):
        ValidationConsumption(repair_id="r", runs_consumed=4)
    with pytest.raises(ValueError):
        ValidationConsumption(
            repair_id="r", runs_consumed=3, outcome="nope",
        )
    with pytest.raises(ValueError):
        ValidationPartialFailure(
            validation_id="v", runs_invoked=0, label="x", error="e",
        )
    assert admission_marker_id("repair-D-H") == "repair-D-H@admission"


def test_ledger_round_trip_preserves_usage_and_fingerprint():
    ledger = RepairBudgetLedger(ledger_id="ledger-test")
    assert ledger.repairs_used == 0
    assert ledger.validation_runs_used == 0
    ledger = ledger.admit(
        repair_id="r1", diagnostic_id="d", hypothesis_id="h",
    )
    ledger = ledger.record_validation(
        repair_id="r1", runs_consumed=3, outcome=COMPLETED_OUTCOME,
    )
    ledger = ledger.admit(
        repair_id="r2", diagnostic_id="d", hypothesis_id="h",
    )
    ledger = ledger.record_validation(
        repair_id="r2", runs_consumed=1, outcome=PARTIAL_OUTCOME,
    )
    assert ledger.repairs_used == 2
    assert ledger.validation_runs_used == 4
    revived = RepairBudgetLedger.from_dict(ledger.to_dict())
    assert revived.to_dict() == ledger.to_dict()
    assert revived.fingerprint() == ledger.fingerprint()
    assert revived.repairs_used == 2
    assert revived.validation_runs_used == 4
    with pytest.raises(ValueError):
        RepairBudgetLedger.from_dict({**ledger.to_dict(), "zzz": 1})


# -- repair budget: refusal and consumption (zero episodes) --------------

def test_max_repairs_zero_refuses_before_any_work():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = HoldAgent()
    provider = SpyBrokenProvider()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(0, 0, 0, 0, 0)
    )
    before = _ledger_of(state).fingerprint()
    with pytest.raises(ValueError):
        _run(state, baseline, agent, provider)
    assert provider.calls == 0
    assert _ledger_of(state).fingerprint() == before
    assert _ledger_of(state).repairs_used == 0
    assert state.evaluation_state.repair_candidates == ()


def test_max_repairs_one_admits_first_refuses_second():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = HoldAgent()
    provider = SpyBrokenProvider()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 1, None, None)
    )
    result, report, analysis, live = _run(state, baseline, agent, provider)
    assert result.decision is RepairDecision.FAILED
    assert (result, report, analysis, live)[1:] == (None, None, None)
    assert provider.calls == 1
    assert _ledger_of(state).repairs_used == 1
    before = _ledger_of(state).fingerprint()
    with pytest.raises(ValueError):
        _run(state, baseline, agent, provider)
    assert provider.calls == 1
    assert _ledger_of(state).fingerprint() == before
    assert _ledger_of(state).repairs_used == 1


def test_failed_repair_consumes_one_repair_unit():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = HoldAgent()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, None, None)
    )
    result, _, _, _ = _run(
        state, baseline, agent, SpyBrokenProvider(),
    )
    assert result.decision is RepairDecision.FAILED
    assert _ledger_of(state).repairs_used == 1
    assert _ledger_of(state).validation_runs_used == 0


def test_replay_produces_identical_accounting_and_fingerprint():
    def _once():
        baseline = make_repair_baseline(dict(_METRICS))
        state = make_repair_state(
            baseline, budget=EvaluationBudget(None, 10, 5, None, None)
        )
        _run(state, baseline, HoldAgent(), SpyBrokenProvider())
        return _ledger_of(state)

    first, second = _once(), _once()
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint() == second.fingerprint()
    assert first.repairs_used == second.repairs_used == 1


def test_fingerprint_changes_when_accounting_changes():
    baseline = make_repair_baseline(dict(_METRICS))
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, None, None)
    )
    before = _ledger_of(state).fingerprint()
    _run(state, baseline, HoldAgent(), SpyBrokenProvider())
    assert _ledger_of(state).fingerprint() != before


def test_admission_marker_is_metadata_not_candidate_evidence():
    baseline = make_repair_baseline(dict(_METRICS))
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, None, None)
    )
    _run(state, baseline, HoldAgent(), SpyBrokenProvider())
    candidates = state.evaluation_state.repair_candidates
    assert len(candidates) == 1
    marker = candidates[0]
    assert marker["record_kind"] == ADMISSION_RECORD_KIND
    assert marker["candidate_id"].endswith("@admission")
    assert "@candidate-" not in marker["candidate_id"]
    # Frozen E2-A usage surface is untouched by accounting.
    assert state.budget_usage() == {"tests": 0}


# -- validation budget gating (zero episodes) ----------------------------

def test_validation_budget_below_three_refuses_before_execution():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = HoldAgent()
    provider = SpyBrokenProvider()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, 2, None)
    )
    with pytest.raises(ValueError):
        _run(state, baseline, agent, provider)
    assert provider.calls == 0
    assert _ledger_of(state).repairs_used == 0
    assert _ledger_of(state).validation_runs_used == 0
    assert state.evaluation_state.repair_candidates == ()


# -- heavy: real E1 validation episodes ----------------------------------

def test_rejected_repair_consumes_repair_and_validation():
    from evaluation.diagnostics.repair.proposal import RepairProposal

    baseline = make_repair_baseline(dict(_ACCEPT_METRICS))
    agent = TripleAgent()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, None, None)
    )

    class HoldAllProvider:
        deterministic = True
        method = "test-hold-all"
        version = "v1"

        def propose(self, **kwargs):
            params = dict(kwargs)
            params["method"] = self.method
            params["method_version"] = self.version
            params["parameters"] = {"rules": [{"type": "hold_all"}]}
            params["rationale"] = "budget test forcing inactivity"
            params["target_metric"] = "turnover"
            from evaluation.diagnostics.contracts.predictions import (
                ExpectedDirection,
            )

            params["target_direction"] = ExpectedDirection.DECREASE
            params["provenance"] = {"provider": "HoldAllBudget"}
            return RepairProposal(**params)

    result, report, analysis, live = _run(
        state, baseline, agent, HoldAllProvider(),
    )
    assert result.decision is RepairDecision.REJECTED
    assert live is not None
    ledger = _ledger_of(state)
    assert ledger.repairs_used == 1
    assert ledger.validation_runs_used == 3
    # Provenance note is last; admission marker precedes it.
    candidates = state.evaluation_state.repair_candidates
    assert candidates[-1]["candidate_id"] == result.candidate_id
    assert "record_kind" not in candidates[-1]
    assert candidates[-2]["record_kind"] == ADMISSION_RECORD_KIND
    validations = state.evaluation_state.validation_results
    assert validations[-1]["validation_runs_consumed"] == 3
    assert validations[-1]["repair_id"] == result.repair_id


def test_max_validation_runs_three_allows_one_then_refuses():
    baseline = make_repair_baseline(dict(_ACCEPT_METRICS))
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 2, 3, None)
    )
    provider = SpyDelegateProvider()
    result, report, analysis, live = _run(
        state, baseline, TripleAgent(), provider,
    )
    assert result.decision is RepairDecision.ACCEPTED
    assert [run.label for run in report.runs] == [
        "candidate_diagnostic",
        "candidate_heldout",
        "original_heldout",
    ]
    assert _ledger_of(state).validation_runs_used == 3
    with pytest.raises(ValueError):
        _run(state, baseline, TripleAgent(), provider)
    assert provider.calls == 1
    assert _ledger_of(state).repairs_used == 1
    assert _ledger_of(state).validation_runs_used == 3


def test_partial_validation_failure_records_invoked_runs_without_rollback():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = ExplodingAgent()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, None, None)
    )
    result, report, analysis, live = _run(
        state, baseline, agent, SpyDelegateProvider(),
    )
    assert result.decision is RepairDecision.FAILED
    assert result.suggested_stopping is not None
    assert report is None and live is None
    ledger = _ledger_of(state)
    assert ledger.repairs_used == 1
    assert ledger.validation_runs_used == 1
    validations = state.evaluation_state.validation_results
    assert len(validations) == 1
    assert validations[0]["validation_runs_consumed"] == 1
    assert validations[0]["outcome"] == PARTIAL_OUTCOME
    # Ledger round-trips after partial failure (revised C8).
    revived = RepairBudgetLedger.from_dict(ledger.to_dict())
    assert revived.fingerprint() == ledger.fingerprint()
    rebuilt = RepairBudgetLedger.from_evaluation_state(
        state.evaluation_state
    )
    assert rebuilt.to_dict() == ledger.to_dict()


def test_ledger_round_trip_after_completed_validation():
    baseline = make_repair_baseline(dict(_ACCEPT_METRICS))
    state = make_repair_state(
        baseline, budget=EvaluationBudget(None, 10, 5, None, None)
    )
    result, _, _, _ = _run(state, baseline, TripleAgent(), SpyDelegateProvider())
    assert result.decision is RepairDecision.ACCEPTED
    ledger = _ledger_of(state)
    revived = RepairBudgetLedger.from_dict(ledger.to_dict())
    assert revived.to_dict() == ledger.to_dict()
    assert revived.fingerprint() == ledger.fingerprint()
