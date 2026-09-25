"""E4-E.1 identity scope: C0 branch-matrix equivalence + attestation.

Part 1 pins the machine-checkable base-policy relationship: the
contextual benchmark with empty context behaves identically to the
frozen volatility-threshold benchmark across the full branch matrix
(boundaries, cash gates, reduce paths, malformed inputs, call counts).

Part 2 covers the IdentityScopeAttestation contract and its
adversarial refusals. Retrieval stays exact-match throughout.
"""

import pytest

from benchmarks.volatility_threshold import VolatilityThresholdBenchmark
from evaluation.context.benchmark import ContextualThresholdBenchmark

from ..benchmarks.fixtures import FakeObservation, make_obs


def _obs_matrix():
    return [
        {"vix": 12.5},
        {"vix": 14.999},
        {"vix": 15.0},
        {"vix": 15.001},
        {"vix": 20.0},
        {"vix": 24.999},
        {"vix": 25.0},
        {"vix": 25.001},
        {"vix": 30.0},
        {"vix": None},
        {"vix": "absent"},
        {"vix": "nonnumeric"},
        {"vix": 12.5, "cash": 0.0},
        {"vix": 12.5, "cash": 0.5},
        {"vix": 12.5, "cash": 1.0},
        {"vix": 30.0, "positions": {
            "nse_equity:RELIANCE:EQ": 4.0,
            "nse_equity:TCS:EQ": 2.0,
        }},
        {"vix": 30.0, "positions": {"nse_equity:TCS:EQ": 0.5}},
        {"vix": 30.0, "positions": {"nse_equity:UNLISTED:EQ": 5.0}},
        {"vix": 12.5, "positions": {
            "nse_equity:RELIANCE:EQ": 4.0,
        }},
        {"vix": 20.0, "positions": {
            "nse_equity:RELIANCE:EQ": 4.0,
        }},
    ]


def test_c0_branch_matrix_matches_frozen():
    frozen = VolatilityThresholdBenchmark()
    fresh = ContextualThresholdBenchmark()
    assert fresh.learned_contexts == ()
    for kwargs in _obs_matrix():
        obs = make_obs(**kwargs)
        assert fresh.act(dict(obs)) == frozen.act(dict(obs)), kwargs


def test_c0_call_count_parity_and_reset():
    frozen = VolatilityThresholdBenchmark()
    fresh = ContextualThresholdBenchmark()
    for kwargs in ({"vix": 12.5}, {"vix": 30.0}, {"vix": None}):
        obs = make_obs(**kwargs)
        fresh.act(dict(obs))
        frozen.act(dict(obs))
    assert fresh.calls == frozen.calls == 3
    fresh.reset()
    assert fresh.calls == 0
    assert fresh.learned_contexts == ()


def test_c0_malformed_observation_parity():
    frozen = VolatilityThresholdBenchmark()
    fresh = ContextualThresholdBenchmark()
    with pytest.raises(TypeError):
        frozen.act(FakeObservation({"no": "schema"}))
    with pytest.raises(TypeError):
        fresh.act(FakeObservation({"no": "schema"}))


# ---------------------------------------------------------------------------
# Part 2: IdentityScopeAttestation + resolve_delivery_scope
# ---------------------------------------------------------------------------

from benchmarks.volatility_threshold import VolatilityThresholdBenchmark as _Frozen
from evaluation.context.assembly import assemble, deliver
from evaluation.context.extraction import extract_candidate
from evaluation.context.gate import adjudicate
from evaluation.context.identity_scope import (
    DELIVERY_AGENT_ID,
    DELIVERY_AGENT_VERSION,
    EXPECTED_BASE_CONSTANTS,
    IDENTITY_SCOPE_METHOD,
    IDENTITY_SCOPE_VERSION,
    SOURCE_AGENT_ID,
    SOURCE_AGENT_VERSION,
    SOURCE_POLICY_FINGERPRINT,
    IdentityScopeAttestation,
    resolve_delivery_scope,
)
from evaluation.context.memory import MemoryStore
from evaluation.context.retrieval import retrieve
from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.regression import analyze_regression
from evaluation.diagnostics.repair.results import RepairDecision, RepairResult
from evaluation.diagnostics.repair.validation import (
    ValidationReport,
    ValidationRun,
)


def _scope_proposal(**overrides):
    params = {
        "repair_id": "repair-D-H-turnover",
        "diagnostic_id": "D",
        "baseline_evaluation_id": "B-R",
        "baseline_fingerprint": "bfp",
        "diagnostic_state_fingerprint": "dfp",
        "target_agent_identity": AgentIdentity(
            SOURCE_AGENT_ID, SOURCE_AGENT_VERSION
        ),
        "target_agent_fingerprint": "tfp",
        "hypothesis_id": "H-turnover",
        "hypothesis_fingerprint": "hfp",
        "failure_class": "turnover",
        "evidence_refs": ("E-1",),
        "target_metric": "turnover",
        "target_direction": ExpectedDirection.DECREASE,
        "method": "rule-table",
        "method_version": "v1",
        "parameters": {"rules": [{"type": "per_session_order_cap"}]},
        "rationale": "throttle per-session order flow",
        "provenance": {"provider": "DeterministicRuleProvider"},
    }
    params.update(overrides)
    return RepairProposal(**params)


def _scope_report():
    runs = (
        ValidationRun(
            label="candidate_diagnostic",
            window=("2023-02-01", "2023-02-28"),
            result_fingerprint="rfp-1",
            metrics={"turnover": 1.5},
        ),
        ValidationRun(
            label="candidate_heldout",
            window=("2023-03-01", "2023-03-31"),
            result_fingerprint="rfp-2",
            metrics={"turnover": 1.2},
        ),
        ValidationRun(
            label="original_heldout",
            window=("2023-03-01", "2023-03-31"),
            result_fingerprint="rfp-3",
            metrics={"turnover": 2.0},
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


def _scope_chain(**proposal_overrides):
    proposal = _scope_proposal(**proposal_overrides)
    report = _scope_report()
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
    store_c0 = MemoryStore(store_id="mem-scope")
    transitioned, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store_c0,
        proposal=proposal,
    )
    assert verdict.decision.value == "ADMITTED"
    store_c1 = store_c0.admit(transitioned, verdict)
    return proposal, result, report, analysis, transitioned, verdict, store_c1


def test_scope_pins_match_manifest_and_live_code():
    import pathlib

    import yaml

    manifest = yaml.safe_load(
        (pathlib.Path(__file__).resolve().parent.parent.parent
         / "benchmarks" / "manifest.yaml").read_text()
    )
    row = [
        r for r in manifest["benchmarks"]
        if r["agent_id"] == SOURCE_AGENT_ID
    ][0]
    assert row["version"] == SOURCE_AGENT_VERSION
    assert row["fingerprint"] == SOURCE_POLICY_FINGERPRINT
    live = _Frozen()
    assert fingerprint_agent(live, live.identity) == (
        SOURCE_POLICY_FINGERPRINT
    )
    assert live.identity.agent_id == SOURCE_AGENT_ID
    assert getattr(_Frozen, "adapt", None) is None
    constants = manifest["class_b_constants"]
    assert constants["vix_low"] == EXPECTED_BASE_CONSTANTS["VIX_LOW"]
    assert constants["vix_high"] == EXPECTED_BASE_CONSTANTS["VIX_HIGH"]
    assert constants["vix_slot"] == EXPECTED_BASE_CONSTANTS["VIX_SLOT"]
    assert list(constants["nse_equity_names"]) == list(
        EXPECTED_BASE_CONSTANTS["NSE_EQUITY_NAMES"]
    )
    assert constants["build_quantity"] == (
        EXPECTED_BASE_CONSTANTS["BUILD_QUANTITY"]
    )
    assert constants["reduce_quantity"] == (
        EXPECTED_BASE_CONSTANTS["REDUCE_QUANTITY"]
    )
    assert constants["cash_dust"] == EXPECTED_BASE_CONSTANTS["CASH_DUST"]
    assert constants["max_orders_per_session"] == (
        EXPECTED_BASE_CONSTANTS["MAX_ORDERS_PER_SESSION"]
    )


def test_resolve_happy_path_and_end_to_end_delivery():
    proposal, _r, _rep, _a, transitioned, verdict, store_c1 = (
        _scope_chain()
    )
    probe = ContextualThresholdBenchmark()
    scope_str, attestation = resolve_delivery_scope(
        candidate=transitioned,
        proposal=proposal,
        verdict=verdict,
        store=store_c1,
        delivery_agent=probe,
    )
    assert scope_str == f"{SOURCE_AGENT_ID}@{SOURCE_AGENT_VERSION}"
    assert attestation.method == IDENTITY_SCOPE_METHOD
    assert attestation.method_version == IDENTITY_SCOPE_VERSION
    assert attestation.delivery_agent_id == DELIVERY_AGENT_ID
    assert attestation.delivery_version == DELIVERY_AGENT_VERSION
    assert attestation.store_fingerprint == store_c1.fingerprint()
    assert IdentityScopeAttestation.from_dict(
        attestation.to_dict()
    ) == attestation
    # Attested retrieval finds the entry; unattested delivery identity
    # does not (exact-match retrieval untouched).
    contexts, record = retrieve(store_c1, agent_id=scope_str)
    assert len(contexts) == 1
    empty, _ = retrieve(store_c1, agent_id=str(probe.identity))
    assert empty == ()
    package = assemble(
        contexts, record, store_c1.fingerprint(), probe.identity
    )
    adapted, _delivery = deliver(
        ContextualThresholdBenchmark(), package, store_c1
    )
    assert len(adapted.learned_contexts) == 1


def test_resolve_refuses_foreign_source_identity():
    _p, _r, _rep, _a, transitioned, verdict, store_c1 = _scope_chain(
        target_agent_identity=AgentIdentity("other-agent", "9.9"),
    )
    # Candidate now carries a foreign source string.
    assert transitioned.agent_id == "other-agent@9.9"
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=transitioned,
            proposal=_p,
            verdict=verdict,
            store=store_c1,
            delivery_agent=ContextualThresholdBenchmark(),
        )


def test_resolve_refuses_proposal_mismatch_and_bad_verdict():
    proposal, _r, _rep, _a, transitioned, verdict, store_c1 = (
        _scope_chain()
    )
    other_proposal = _scope_proposal(repair_id="repair-other")
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=transitioned,
            proposal=other_proposal,
            verdict=verdict,
            store=store_c1,
            delivery_agent=ContextualThresholdBenchmark(),
        )
    rejected = verdict.to_dict()
    rejected["decision"] = "REJECTED"
    from evaluation.context.gate import AdmissionVerdict

    bad_verdict = AdmissionVerdict.from_dict(rejected)
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=transitioned,
            proposal=proposal,
            verdict=bad_verdict,
            store=store_c1,
            delivery_agent=ContextualThresholdBenchmark(),
        )


def test_resolve_refuses_wrong_or_contextualised_delivery_agent():
    proposal, _r, _rep, _a, transitioned, verdict, store_c1 = (
        _scope_chain()
    )
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=transitioned,
            proposal=proposal,
            verdict=verdict,
            store=store_c1,
            delivery_agent=_Frozen(),
        )
    used = ContextualThresholdBenchmark()
    used.adapt({"entries": [{
        "context_id": "ctx-x",
        "failure_mechanism": "turnover",
        "corrective_principle": "c",
    }]})
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=transitioned,
            proposal=proposal,
            verdict=verdict,
            store=store_c1,
            delivery_agent=used,
        )


def test_resolve_refuses_unadmitted_or_foreign_store():
    proposal, _r, _rep, _a, transitioned, verdict, store_c1 = (
        _scope_chain()
    )
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=transitioned,
            proposal=proposal,
            verdict=verdict,
            store=MemoryStore(store_id="mem-empty"),
            delivery_agent=ContextualThresholdBenchmark(),
        )
    non_candidate, _v2 = transitioned, verdict
    from evaluation.context.learned import ContextStatus

    rogue = non_candidate.with_status(ContextStatus.QUARANTINED)
    with pytest.raises(ValueError):
        resolve_delivery_scope(
            candidate=rogue,
            proposal=proposal,
            verdict=verdict,
            store=store_c1,
            delivery_agent=ContextualThresholdBenchmark(),
        )


def test_attestation_round_trip_and_unknown_fields():
    proposal, _r, _rep, _a, transitioned, verdict, store_c1 = (
        _scope_chain()
    )
    _, attestation = resolve_delivery_scope(
        candidate=transitioned,
        proposal=proposal,
        verdict=verdict,
        store=store_c1,
        delivery_agent=ContextualThresholdBenchmark(),
    )
    first = attestation.fingerprint()
    assert IdentityScopeAttestation.from_dict(
        attestation.to_dict()
    ).fingerprint() == first
    with pytest.raises(ValueError):
        IdentityScopeAttestation.from_dict(
            {**attestation.to_dict(), "surprise": 1}
        )
