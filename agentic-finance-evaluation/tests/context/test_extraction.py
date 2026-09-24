"""E4-B extraction tests: deterministic, evidence-preserving, pure."""

import pytest

from evaluation.context.extraction import (
    EXTRACTION_METHOD,
    EXTRACTION_VERSION,
    extract_candidate,
)
from evaluation.context.learned import ContextStatus
from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.regression import analyze_regression
from evaluation.diagnostics.repair.results import RepairDecision, RepairResult
from evaluation.diagnostics.repair.validation import (
    ValidationReport,
    ValidationRun,
)


def _proposal(**overrides):
    params = {
        "repair_id": "repair-D-H-1",
        "diagnostic_id": "D",
        "baseline_evaluation_id": "B-R",
        "baseline_fingerprint": "bfp",
        "diagnostic_state_fingerprint": "dfp",
        "target_agent_identity": AgentIdentity("churn-stub", "0.1"),
        "target_agent_fingerprint": "tfp",
        "hypothesis_id": "H-1",
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


def _report(**overrides):
    runs = (
        ValidationRun(
            label="candidate_diagnostic",
            window=("2023-05-15", "2023-05-26"),
            result_fingerprint="rfp-1",
            metrics={"turnover": 1.5},
        ),
        ValidationRun(
            label="candidate_heldout",
            window=("2023-06-01", "2023-06-30"),
            result_fingerprint="rfp-2",
            metrics={"turnover": 1.2},
        ),
        ValidationRun(
            label="original_heldout",
            window=("2023-06-01", "2023-06-30"),
            result_fingerprint="rfp-3",
            metrics={"turnover": 2.0},
        ),
    )
    params = {
        "validation_id": "V-1",
        "candidate_id": "churn-stub@candidate-1",
        "candidate_fingerprint": "cfp",
        "baseline_evaluation_id": "B-R",
        "baseline_fingerprint": "bfp",
        "runs": runs,
        "method": "e1-rerun-comparison",
        "method_version": "v1",
    }
    params.update(overrides)
    return ValidationReport(**params)


def _result(proposal, report, analysis, **overrides):
    params = {
        "repair_id": proposal.repair_id,
        "proposal_fingerprint": proposal.fingerprint(),
        "candidate_id": "churn-stub@candidate-1",
        "candidate_fingerprint": "cfp",
        "validation_fingerprint": report.fingerprint(),
        "analysis_fingerprint": analysis.fingerprint(),
        "decision": RepairDecision.ACCEPTED,
        "reason": "target improved",
        "method": "rule-table",
        "method_version": "v1",
    }
    params.update(overrides)
    return RepairResult(**params)


def _analysis(report):
    return analyze_regression(
        analysis_id="A-1",
        candidate_id="churn-stub@candidate-1",
        validation_fingerprint=report.fingerprint(),
        comparisons=(
            ("candidate_diagnostic", "turnover", 2.5, 1.5),
            ("candidate_heldout", "turnover", 2.0, 1.2),
        ),
    )


def _artefacts(**overrides):
    proposal = _proposal(**overrides.get("proposal", {}))
    report = _report()
    analysis = _analysis(report)
    result = _result(proposal, report, analysis)
    return proposal, result, report, analysis


def test_extraction_deterministic_and_candidate():
    first = extract_candidate(**dict(zip(
        ("proposal", "result", "report", "analysis"), _artefacts()
    )))
    second = extract_candidate(**dict(zip(
        ("proposal", "result", "report", "analysis"), _artefacts()
    )))
    assert first == second
    assert first.fingerprint() == second.fingerprint()
    assert first.status is ContextStatus.CANDIDATE
    assert first.context_id == f"ctx-{first.provenance['proposal_fingerprint'][:16]}"


def test_extraction_preserves_provenance_and_evidence():
    proposal, result, report, analysis = _artefacts()
    candidate = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    assert candidate.agent_id == "churn-stub@0.1"
    assert candidate.source_evaluation_id == "B-R"
    assert candidate.failure_mechanism == "turnover"
    assert candidate.diagnostic_evidence == ("E-1",)
    assert candidate.validation_result == "ACCEPTED"
    assert candidate.validation_metrics["delta"] == pytest.approx(-1.0)
    assert candidate.held_out_evidence["candidate_heldout"]["delta"] == (
        pytest.approx(-0.8)
    )
    assert candidate.held_out_evidence["original_heldout"][
        "target_value"
    ] == pytest.approx(2.0)
    assert candidate.provenance["repair_fingerprint"] == result.fingerprint()
    assert candidate.provenance["extraction_method"] == EXTRACTION_METHOD
    assert candidate.provenance["extraction_version"] == EXTRACTION_VERSION
    assert "turnover" in candidate.observed_pattern
    assert "DECREASE" in candidate.corrective_principle


def test_extraction_is_pure_no_mutation():
    proposal, result, report, analysis = _artefacts()
    before = (
        proposal.fingerprint(),
        result.fingerprint(),
        report.fingerprint(),
        analysis.fingerprint(),
    )
    extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    assert before == (
        proposal.fingerprint(),
        result.fingerprint(),
        report.fingerprint(),
        analysis.fingerprint(),
    )


def test_mismatched_artefacts_refused():
    proposal, result, report, analysis = _artefacts()
    other = _proposal(repair_id="repair-D-H-2")
    with pytest.raises(ValueError):
        extract_candidate(
            proposal=other, result=result, report=report, analysis=analysis
        )
    with pytest.raises(TypeError):
        extract_candidate(
            proposal="nope", result=result, report=report, analysis=analysis
        )


def test_missing_target_finding_refused_not_invented():
    proposal = _proposal(target_metric="sharpe_per_session")
    report = _report()
    analysis = _analysis(report)
    result = _result(proposal, report, analysis)
    with pytest.raises(ValueError):
        extract_candidate(
            proposal=proposal, result=result, report=report,
            analysis=analysis,
        )


def test_undefined_values_rendered_not_crashed():
    proposal, result, report, analysis = _artefacts()
    assert "1.5" in extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    ).observed_pattern
