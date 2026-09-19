"""End-to-end run_repair tests with real validation episodes.

A local triple-order stub makes the v1 guardrail bind, so the repaired
candidate measurably differs from the original. A hand-crafted hold_all
proposal proves permanent inactivity is rejected, not celebrated.
"""

from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.repair.application import apply_repair
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.results import RepairDecision, run_repair

from .fixtures import make_repair_baseline, make_repair_state

_HELDOUT = ("2023-06-01", "2023-06-30")
_METRICS = {
    "turnover": 5.0,
    "cumulative_return": -0.5,
    "inactivity_rate": 0.0,
    "invalid_order_count": 0.0,
    "universe_violation_count": 0.0,
    "no_price_count": 0.0,
    "calendar_gate_count": 0.0,
}


class TripleAgent:
    """Submits three orders per session so the order cap binds."""

    identity = AgentIdentity("triple-stub", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        return [
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "side": "BUY",
                "quantity": 1.0,
            }
            for _ in range(3)
        ]


def test_accepted_repair_end_to_end():
    baseline = make_repair_baseline(dict(_METRICS))
    agent = TripleAgent()
    state = make_repair_state(baseline)
    result, report, analysis, live = run_repair(
        diagnostic_state=state,
        baseline=baseline,
        original_agent=agent,
        hypothesis_id="H-1",
        heldout_window=_HELDOUT,
        seed=7,
    )
    assert result.decision is RepairDecision.ACCEPTED
    assert result.suggested_stopping is None
    assert live is not None
    assert [run.label for run in report.runs] == [
        "candidate_diagnostic",
        "candidate_heldout",
        "original_heldout",
    ]
    assert analysis.finding("turnover", "candidate_diagnostic").delta < 0
    assert result.fingerprint()
    # Provenance anchored on the diagnostic state's E0 slots.
    candidates = state.evaluation_state.repair_candidates
    assert candidates[-1]["candidate_id"] == result.candidate_id
    validations = state.evaluation_state.validation_results
    assert validations[-1]["candidate_id"] == result.candidate_id
    assert (
        validations[-1]["decision"] == RepairDecision.ACCEPTED.value
    )


def test_permanent_inactivity_is_rejected_not_celebrated():
    from evaluation.diagnostics.repair.proposal import RepairProposal

    baseline = make_repair_baseline(dict(_METRICS))
    agent = TripleAgent()
    state = make_repair_state(baseline)

    class HoldAllProvider:
        deterministic = True
        method = "test-hold-all"
        version = "v1"

        def propose(self, **kwargs):
            params = dict(kwargs)
            params["method"] = self.method
            params["method_version"] = self.version
            params["parameters"] = {"rules": [{"type": "hold_all"}]}
            params["rationale"] = (
                "test-only provider forcing permanent inactivity"
            )
            params["target_metric"] = "turnover"
            from evaluation.diagnostics.contracts.predictions import (
                ExpectedDirection,
            )

            params["target_direction"] = ExpectedDirection.DECREASE
            params["provenance"] = {"provider": "HoldAllProvider"}
            return RepairProposal(**params)

    result, report, analysis, live = run_repair(
        diagnostic_state=state,
        baseline=baseline,
        original_agent=agent,
        hypothesis_id="H-1",
        heldout_window=_HELDOUT,
        seed=7,
        provider=HoldAllProvider(),
    )
    assert live is not None
    assert report.run("candidate_diagnostic").metrics["inactivity_rate"] == 1.0
    assert result.decision is RepairDecision.REJECTED
    assert "inactivity" in result.reason
