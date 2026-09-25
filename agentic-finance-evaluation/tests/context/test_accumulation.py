"""E4-F accumulation wiring: dual-guard instrument, v2 scope, cycles.

Cheap only (no market episodes): C0 equivalence and guard divergence
on hand-built observations; attested C1->C2 admission chains on
frozen-artefact fixtures; T12 vs accumulation wiring; retention and
duplicate-refusal proofs.
"""

import pytest

from benchmarks.volatility_threshold import VolatilityThresholdBenchmark
from evaluation.context.accumulating_benchmark import (
    EXPOSURE_MECHANISM,
    TURNOVER_MECHANISM,
    AccumulatingThresholdBenchmark,
)
from evaluation.context.assembly import assemble, deliver
from evaluation.context.cycles import (
    E4FCycleResult,
    accumulation_delta,
    apply_dual_temporary,
    assert_retained,
    build_dual_temporary_payload,
    retention_proof,
)
from evaluation.context.extraction import extract_candidate
from evaluation.context.gate import AdmissionDecision, adjudicate
from evaluation.context.identity_scope import resolve_delivery_scope
from evaluation.context.memory import MemoryStore
from evaluation.context.retrieval import retrieve
from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.regression import analyze_regression
from evaluation.diagnostics.repair.results import RepairDecision, RepairResult
from evaluation.diagnostics.repair.validation import (
    ValidationReport,
    ValidationRun,
)

from ..benchmarks.fixtures import make_obs


def _entry(mechanism, context_id="ctx-1"):
    return {
        "context_id": context_id,
        "failure_mechanism": mechanism,
        "corrective_principle": "c",
    }


def _held_obs():
    return make_obs(
        vix=12.5, positions={"nse_equity:RELIANCE:EQ": 4.0}
    )


def test_accumulating_c0_matches_frozen():
    frozen = VolatilityThresholdBenchmark()
    fresh = AccumulatingThresholdBenchmark()
    assert fresh.identity.agent_id == "accumulating-threshold-benchmark"
    for kwargs in (
        {"vix": 12.5},
        {"vix": 15.0},
        {"vix": 20.0},
        {"vix": 25.0},
        {"vix": 30.0},
        {"vix": None},
        {"vix": "absent"},
        {"vix": 12.5, "cash": 0.0},
        {"vix": 30.0, "positions": {
            "nse_equity:RELIANCE:EQ": 4.0,
            "nse_equity:TCS:EQ": 2.0,
        }},
    ):
        obs = make_obs(**kwargs)
        assert fresh.act(dict(obs)) == frozen.act(dict(obs)), kwargs


def test_guards_diverge_by_mechanism():
    turnover_only = AccumulatingThresholdBenchmark()
    turnover_only.adapt({"entries": [_entry(TURNOVER_MECHANISM)]})
    exposure_only = AccumulatingThresholdBenchmark()
    exposure_only.adapt({"entries": [_entry(EXPOSURE_MECHANISM)]})
    both = AccumulatingThresholdBenchmark()
    both.adapt({"entries": [
        _entry(TURNOVER_MECHANISM, "ctx-t"),
        _entry(EXPOSURE_MECHANISM, "ctx-e"),
    ]})
    # Held RELIANCE, LOW regime: turnover guard drops the held-name BUY
    # (depth); exposure guard drops the new-name BUY (breadth).
    assert [o["instrument"] for o in turnover_only.act(
        _held_obs())] == ["TCS:EQ"]
    assert [o["instrument"] for o in exposure_only.act(
        _held_obs())] == ["RELIANCE:EQ"]
    assert [o["instrument"] for o in both.act(_held_obs())] == []
    # Flat portfolio: exposure guard cannot manufacture inactivity.
    assert len(exposure_only.act(make_obs(vix=12.5))) == 2
    # Foreign mechanism stays inert.
    foreign = AccumulatingThresholdBenchmark()
    foreign.adapt({"entries": [_entry("leverage")]})
    assert foreign.act(_held_obs()) == AccumulatingThresholdBenchmark().act(
        _held_obs()
    )


def _proposal(failure_class, metric, principle):
    return RepairProposal(
        repair_id=f"repair-D-H-{failure_class}",
        diagnostic_id="D",
        baseline_evaluation_id="B-R",
        baseline_fingerprint="bfp",
        diagnostic_state_fingerprint="dfp",
        target_agent_identity=AgentIdentity(
            "volatility-threshold-benchmark", "1.0"
        ),
        target_agent_fingerprint="tfp",
        hypothesis_id=f"H-{failure_class}",
        hypothesis_fingerprint="hfp",
        failure_class=failure_class,
        evidence_refs=("E-1",),
        target_metric=metric,
        target_direction=ExpectedDirection.DECREASE,
        method="rule-table",
        method_version="v1",
        parameters={"rules": [{"type": "per_session_order_cap"}]},
        rationale=principle,
        provenance={"provider": "DeterministicRuleProvider"},
    )


def _report(metric, diag_value, held_value):
    runs = (
        ValidationRun(
            label="candidate_diagnostic",
            window=("2023-02-01", "2023-02-28"),
            result_fingerprint="rfp-1",
            metrics={metric: diag_value},
        ),
        ValidationRun(
            label="candidate_heldout",
            window=("2023-03-01", "2023-03-31"),
            result_fingerprint="rfp-2",
            metrics={metric: held_value},
        ),
        ValidationRun(
            label="original_heldout",
            window=("2023-03-01", "2023-03-31"),
            result_fingerprint="rfp-3",
            metrics={metric: 2.0},
        ),
    )
    return ValidationReport(
        validation_id="V-1",
        candidate_id="volatility-threshold-benchmark@candidate-1",
        candidate_fingerprint="cfp",
        baseline_evaluation_id="B-R",
        baseline_fingerprint="bfp",
        runs=runs,
        method="e1-rerun-comparison",
        method_version="v1",
    )


def _admit_chain(failure_class, metric, principle, store):
    proposal = _proposal(failure_class, metric, principle)
    report = _report(metric, 1.5, 1.2)
    analysis = analyze_regression(
        analysis_id="A-1",
        candidate_id="volatility-threshold-benchmark@candidate-1",
        validation_fingerprint=report.fingerprint(),
        comparisons=(
            ("candidate_diagnostic", metric, 2.5, 1.5),
            ("candidate_heldout", metric, 2.0, 1.2),
        ),
    )
    result = RepairResult(
        repair_id=proposal.repair_id,
        proposal_fingerprint=proposal.fingerprint(),
        candidate_id="volatility-threshold-benchmark@candidate-1",
        candidate_fingerprint="cfp",
        validation_fingerprint=report.fingerprint(),
        analysis_fingerprint=analysis.fingerprint(),
        decision=RepairDecision.ACCEPTED,
        reason="target improved",
        method="rule-table",
        method_version="v1",
    )
    candidate = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    transitioned, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store,
        proposal=proposal,
    )
    assert verdict.decision is AdmissionDecision.ADMITTED
    return proposal, transitioned, verdict, store.admit(transitioned, verdict)


def test_c1_to_c2_accumulation_and_retention():
    _p1, t1, v1, store_c1 = _admit_chain(
        "turnover", "turnover", "throttle accumulation",
        MemoryStore(store_id="mem-acc"),
    )
    before = retention_proof(store_c1)
    assert store_c1.store_version == 1
    _p2, t2, v2, store_c2 = _admit_chain(
        "exposure", "gross_exposure_max", "restrict breadth", store_c1
    )
    assert store_c2.store_version == 2
    assert [e.sequence for e in store_c2.entries] == [1, 2]
    assert_retained(before, retention_proof(store_c2))
    assert t1.fingerprint() != t2.fingerprint()
    assert t1.context_id != t2.context_id


def test_duplicate_k1_refused_on_cycle_2():
    proposal = _proposal("turnover", "turnover", "throttle accumulation")
    report = _report("turnover", 1.5, 1.2)
    analysis = analyze_regression(
        analysis_id="A-1",
        candidate_id="volatility-threshold-benchmark@candidate-1",
        validation_fingerprint=report.fingerprint(),
        comparisons=(
            ("candidate_diagnostic", "turnover", 2.5, 1.5),
            ("candidate_heldout", "turnover", 2.0, 1.2),
        ),
    )
    result = RepairResult(
        repair_id=proposal.repair_id,
        proposal_fingerprint=proposal.fingerprint(),
        candidate_id="volatility-threshold-benchmark@candidate-1",
        candidate_fingerprint="cfp",
        validation_fingerprint=report.fingerprint(),
        analysis_fingerprint=analysis.fingerprint(),
        decision=RepairDecision.ACCEPTED,
        reason="target improved",
        method="rule-table",
        method_version="v1",
    )
    candidate = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    store_c0 = MemoryStore(store_id="mem-acc")
    transitioned, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store_c0,
        proposal=proposal,
    )
    store_c1 = store_c0.admit(transitioned, verdict)
    assert store_c1.contains(transitioned.fingerprint())
    # Re-presenting identical knowledge to the Cycle-2 gate refuses.
    candidate_b = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    assert candidate_b.fingerprint() == candidate.fingerprint()
    _same, verdict_b = adjudicate(
        candidate=candidate_b,
        result=result,
        report=report,
        analysis=analysis,
        store=store_c1,
        proposal=proposal,
    )
    assert verdict_b.decision.value == "DUPLICATE"


def test_v2_scope_serves_accumulating_agent():
    _p1, t1, v1, store_c1 = _admit_chain(
        "turnover", "turnover", "throttle accumulation",
        MemoryStore(store_id="mem-acc"),
    )
    probe = AccumulatingThresholdBenchmark()
    # v1 scope refuses the accumulating representation (closed scope).
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=t1,
            proposal=_p1,
            verdict=v1,
            store=store_c1,
            delivery_agent=probe,
        )
    scope_str, attestation = resolve_delivery_scope(
        candidate=t1,
        proposal=_p1,
        verdict=v1,
        store=store_c1,
        delivery_agent=probe,
        scope_version="v2",
    )
    assert attestation.method_version == "v2"
    contexts, record = retrieve(store_c1, agent_id=scope_str)
    package = assemble(
        contexts, record, store_c1.fingerprint(), probe.identity
    )
    adapted, _delivery = deliver(
        AccumulatingThresholdBenchmark(), package, store_c1
    )
    assert len(adapted.learned_contexts) == 1


def test_dual_temporary_is_provisional_and_non_persistent():
    payload = build_dual_temporary_payload(
        [_entry(TURNOVER_MECHANISM, "ctx-t")],
        [_entry(EXPOSURE_MECHANISM, "ctx-e")],
    )
    assert payload["provisional"] is True
    assert "mem-" not in repr(payload)
    agent = AccumulatingThresholdBenchmark()
    adapted = apply_dual_temporary(agent, payload)
    assert adapted is not agent
    assert len(adapted.learned_contexts) == 2
    assert list(agent.learned_contexts) == []
    with pytest.raises(ValueError):
        build_dual_temporary_payload([], [_entry("turnover")])


def test_accumulation_delta_and_result_round_trip():
    out = accumulation_delta(
        {"turnover": 2.0, "gross_exposure_max": 0.9},
        {"turnover": 1.0, "gross_exposure_max": 0.9},
        {"turnover": 1.0, "gross_exposure_max": 0.5},
    )
    assert out["accumulated_vs_C0"]["turnover"] == -1.0
    assert out["accumulated_vs_dual_temp"]["gross_exposure_max"] == -0.4
    assert out["dual_temp_vs_C0"]["gross_exposure_max"] == 0.0
    result = E4FCycleResult(
        experiment_id="e4f-test",
        execution_role="SYSTEM_VALIDATION",
        execution_instance="001",
        protocol_fingerprint="proto",
        windows={"w1": "2023-01-01"},
        cycle_1={},
        cycle_2={},
        terminal={},
        lineage={},
        leakage={},
    )
    assert E4FCycleResult.from_dict(result.to_dict()) == result
    assert result.fingerprint()
    with pytest.raises(ValueError):
        E4FCycleResult.from_dict({**result.to_dict(), "extra": 1})


def test_repair_target_hypothesis_selection():
    from evaluation.contracts.hypotheses import (
        Hypothesis,
        HypothesisStatus,
    )
    from evaluation.diagnostics.contracts.diagnostic_state import (
        DiagnosticState,
    )
    from experiments.harness.errors import ProtocolAmbiguityError
    from experiments.harness.lifecycle import repair_target_hypothesis

    from evaluation.contracts.budget import EvaluationBudget

    def _state():
        return DiagnosticState(
            diagnostic_id="D",
            baseline_evaluation_id="B",
            baseline_fingerprint="fp",
            agent_identity=AgentIdentity("a", "1"),
            environment_spec={"market_fingerprint": "m"},
            config={},
            budget=EvaluationBudget(None, 10, None, None, None),
        )

    def _hypothesis(hid, status):
        return Hypothesis(
            hypothesis_id=hid,
            failure_class=hid.split("-")[1],
            mechanism=f"{hid} mechanism",
            confidence=0.5,
            evidence_refs=("E-1",),
            status=status,
        )

    state = _state()
    for hid in ("H-turnover", "H-exposure"):
        state.register_hypothesis(_hypothesis(hid, "PROPOSED"))
    with pytest.raises(ProtocolAmbiguityError):
        repair_target_hypothesis(state)
    single = _state()
    single.register_hypothesis(_hypothesis("H-turnover", "PROPOSED"))
    single.register_hypothesis(_hypothesis("H-exposure", "SUPPORTED"))
    assert repair_target_hypothesis(single) == "H-exposure"
    both = _state()
    both.register_hypothesis(_hypothesis("H-turnover", "SUPPORTED"))
    both.register_hypothesis(_hypothesis("H-exposure", "SUPPORTED"))
    with pytest.raises(ProtocolAmbiguityError):
        repair_target_hypothesis(both)
