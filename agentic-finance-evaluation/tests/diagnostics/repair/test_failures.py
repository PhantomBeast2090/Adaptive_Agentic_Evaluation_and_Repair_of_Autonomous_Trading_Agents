"""Failure taxonomy tests: each failure mode stays distinct."""

import pytest

from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.repair.results import RepairDecision, run_repair

from ..execution_fixtures import ExplodingAgent, HoldAgent
from .fixtures import make_repair_baseline, make_repair_state

_HELDOUT = ("2023-06-01", "2023-06-30")
_METRICS = {
    "turnover": 2.5,
    "cumulative_return": 0.02,
    "invalid_order_count": 0.0,
    "universe_violation_count": 0.0,
    "no_price_count": 0.0,
    "calendar_gate_count": 0.0,
}


def _run(provider=None, **overrides):
    baseline = make_repair_baseline(dict(_METRICS))
    agent = HoldAgent()
    state = make_repair_state(baseline)
    params = {
        "diagnostic_state": state,
        "baseline": baseline,
        "original_agent": agent,
        "hypothesis_id": "H-1",
        "heldout_window": _HELDOUT,
        "seed": 7,
    }
    if provider is not None:
        params["provider"] = provider
    params.update(overrides)
    return run_repair(**params)


def test_provider_failure_is_failed_not_rejected():
    class BrokenProvider:
        deterministic = True
        method = "broken"
        version = "v1"

        def propose(self, **kwargs):
            raise RuntimeError("provider blew up")

    result, report, analysis, live = _run(provider=BrokenProvider())
    assert result.decision is RepairDecision.FAILED
    assert "provider blew up" in result.reason
    assert result.suggested_stopping is StoppingReason.REPAIR_FAILED
    assert report is None and analysis is None and live is None


def test_exploding_agent_validation_failure_is_failed():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = ExplodingAgent()
    state = make_repair_state(baseline)
    result, report, analysis, live = run_repair(
        diagnostic_state=state,
        baseline=baseline,
        original_agent=agent,
        hypothesis_id="H-1",
        heldout_window=_HELDOUT,
        seed=7,
    )
    assert result.decision is RepairDecision.FAILED
    assert "validation" in result.reason.lower() or "failed" in result.reason.lower()
    assert result.suggested_stopping is StoppingReason.REPAIR_FAILED
    assert live is None


def test_budget_refusal_before_any_work():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = HoldAgent()
    state = make_repair_state(
        baseline, budget=EvaluationBudget(0, 0, 0, 0, 0)
    )
    with pytest.raises(ValueError):
        run_repair(
            diagnostic_state=state,
            baseline=baseline,
            original_agent=agent,
            hypothesis_id="H-1",
            heldout_window=_HELDOUT,
            seed=7,
        )
    assert state.tests_consumed() == 0
    assert len(state.test_results) == 0


def test_repair_failed_suggests_stopping_not_reject():
    assert RepairDecision.FAILED.value == "FAILED"
    assert RepairDecision.REJECTED.value == "REJECTED"
    assert RepairDecision.ACCEPTED.value == "ACCEPTED"
    assert RepairDecision.UNRESOLVED.value == "UNRESOLVED"
    with pytest.raises(ValueError):
        RepairDecision.from_str("MAYBE")
