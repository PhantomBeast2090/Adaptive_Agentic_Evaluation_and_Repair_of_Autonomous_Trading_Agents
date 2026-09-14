"""E1 evidence tests: references, derivation, categories, no diagnosis."""

from evaluation.baseline import run_baseline
from evaluation.baseline.evidence import (
    derive_baseline_evidence,
    evidence_metric_names,
)
from evaluation.contracts.evidence import BehavioralEvidence, EvidenceCategory

from .stubs import BuyOnceAgent, HoldAgent, small_config


def test_evidence_references_valid_record_fingerprints():
    result = run_baseline(HoldAgent(), small_config("E1-EV-01"))
    record_fps = {r.fingerprint() for r in result.decision_records}
    assert len(result.evidence) == 11
    for item in result.evidence:
        assert isinstance(item, BehavioralEvidence)
        assert set(item.decision_refs) == record_fps
        assert item.provenance["market_fingerprint"] == (
            result.environment_spec["market_fingerprint"]
        )


def test_evidence_derivation_categories_and_identity():
    result = run_baseline(BuyOnceAgent(), small_config("E1-EV-02"))
    assert tuple(sorted(evidence_metric_names())) == tuple(
        sorted(item.metric_name for item in result.evidence)
    )
    allowed = set(EvidenceCategory)
    for item in result.evidence:
        assert item.category in allowed
        assert item.derivation["method"].startswith("e1.")
        assert item.derivation["evaluator"] == "e1-baseline"
        assert item.evidence_id == f"E1-E1-EV-02-{item.metric_name}"
    by_name = {item.metric_name: item for item in result.evidence}
    assert by_name["turnover"].category is EvidenceCategory.DECISION_BEHAVIOR
    assert by_name["max_drawdown"].category is EvidenceCategory.RISK
    assert by_name["invalid_order_rate"].category is EvidenceCategory.EXECUTION
    assert (
        by_name["unavailable_info_rate"].category
        is EvidenceCategory.INFORMATION_USAGE
    )
    # Round-trip preserves identity.
    first = result.evidence[0]
    assert BehavioralEvidence.from_dict(first.to_dict()).fingerprint() == (
        first.fingerprint()
    )


def test_no_hypothesis_generated_by_baseline():
    result = run_baseline(HoldAgent(), small_config("E1-EV-03"))
    assert result.evaluation_state.hypotheses == ()
    assert result.evaluation_state.baseline_evidence == tuple(result.evidence)
    assert result.evaluation_state.evidence == ()
    for item in result.evidence:
        assert not hasattr(item, "mechanism")
        assert not hasattr(item, "failure_class")
