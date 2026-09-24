"""Deterministic extraction of candidate knowledge (E4-B).

``extract_candidate`` transforms already-existing validated artefacts
(``RepairProposal`` + ``RepairResult`` + ``ValidationReport`` +
``RegressionAnalysis``) into a ``LearnedContext`` with status
CANDIDATE. It is a pure deterministic function:

* no live market data, no future information;
* no mutation of inputs, agent, or memory;
* no retrieval, no additional validation;
* no invented evidence — every field derives from artefact contents,
  and missing required content fails closed instead of being guessed.

Held-out leakage rule: held-out outcomes are represented only as the
validation evidence already present in the frozen validation
artefact. Extraction derives no new knowledge from held-out data;
it restates what validation already recorded.

Use a validated T1 artefact as a BOOTSTRAP TEST FIXTURE where needed.
A fixture exercises the transformer; it does not demonstrate
autonomous learning and makes no scientific claim: the claim begins
only when the extraction/admission pipeline itself produces the
knowledge object.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.regression import RegressionAnalysis
from evaluation.diagnostics.repair.results import RepairResult
from evaluation.diagnostics.repair.validation import ValidationReport

EXTRACTION_METHOD = "validated-repair-extraction"
EXTRACTION_VERSION = "v1"


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "undefined"
    return repr(float(value))


def _finding_map(finding: Any) -> Dict[str, Any]:
    return {
        "metric": finding.metric_name,
        "window": finding.window_label,
        "reference": finding.reference_value,
        "validation": finding.validation_value,
        "delta": finding.delta,
    }


def extract_candidate(
    *,
    proposal: RepairProposal,
    result: RepairResult,
    report: ValidationReport,
    analysis: RegressionAnalysis,
) -> LearnedContext:
    """Build a CANDIDATE LearnedContext from validated artefacts."""
    for name, value, kind in (
        ("proposal", proposal, RepairProposal),
        ("result", result, RepairResult),
        ("report", report, ValidationReport),
        ("analysis", analysis, RegressionAnalysis),
    ):
        if not isinstance(value, kind):
            raise TypeError(
                f"{name} must be a {kind.__name__}, "
                f"got {type(value).__name__}"
            )
    # Cross-artefact consistency: the four inputs must describe the
    # same repair attempt, or extraction refuses to proceed.
    if result.proposal_fingerprint != proposal.fingerprint():
        raise ValueError(
            "result does not reference this proposal: refusing extraction"
        )
    if result.validation_fingerprint != report.fingerprint():
        raise ValueError(
            "result does not reference this validation report: "
            "refusing extraction"
        )
    if result.analysis_fingerprint != analysis.fingerprint():
        raise ValueError(
            "result does not reference this regression analysis: "
            "refusing extraction"
        )
    try:
        target = analysis.finding(
            proposal.target_metric, "candidate_diagnostic"
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(
            "analysis carries no diagnostic-window finding for the "
            f"proposal target metric {proposal.target_metric!r}: "
            "refusing to invent one"
        ) from exc
    try:
        heldout = analysis.finding(
            proposal.target_metric, "candidate_heldout"
        )
        heldout_map: Optional[Dict[str, Any]] = _finding_map(heldout)
    except (KeyError, ValueError):
        heldout_map = None
    direction = proposal.target_direction
    direction_name = (
        direction.value
        if hasattr(direction, "value")
        else str(direction)
    )
    observed = (
        f"{proposal.target_metric} {direction_name} on "
        f"candidate_diagnostic: "
        f"{_format_number(target.reference_value)} -> "
        f"{_format_number(target.validation_value)} "
        f"(delta {_format_number(target.delta)})"
    )
    windows = tuple(
        f"{run.label}@{run.window[0]}..{run.window[1]}"
        for run in report.runs
    )
    held_out_evidence: Dict[str, Any] = {}
    if heldout_map is not None:
        held_out_evidence["candidate_heldout"] = heldout_map
    try:
        original = report.run("original_heldout")
        held_out_evidence["original_heldout"] = {
            "window": list(original.window),
            "result_fingerprint": original.result_fingerprint,
            "target_value": original.value_of(proposal.target_metric),
        }
    except KeyError:
        pass
    agent_identity = proposal.target_agent_identity
    return LearnedContext(
        context_id=f"ctx-{proposal.fingerprint()[:16]}",
        agent_id=str(agent_identity),
        source_evaluation_id=proposal.baseline_evaluation_id,
        failure_mechanism=proposal.failure_class,
        observed_pattern=observed,
        triggering_conditions=tuple(
            sorted({target.window_label, "candidate_heldout"})
        ),
        diagnostic_evidence=tuple(proposal.evidence_refs),
        corrective_principle=(
            f"{direction_name} {proposal.target_metric} via "
            f"{proposal.method} {proposal.method_version}: "
            f"{proposal.rationale}"
        ),
        applicability_conditions=windows,
        contraindications=(),
        expected_effect=(
            f"expected {direction_name} in {proposal.target_metric}; "
            f"observed delta {_format_number(target.delta)} on "
            "candidate_diagnostic"
        ),
        validation_result=result.decision.value
        if hasattr(result.decision, "value")
        else str(result.decision),
        validation_metrics=_finding_map(target),
        held_out_evidence=held_out_evidence,
        provenance={
            "proposal_fingerprint": proposal.fingerprint(),
            "proposal_method": proposal.method,
            "proposal_version": proposal.method_version,
            "repair_id": result.repair_id,
            "repair_fingerprint": result.fingerprint(),
            "validation_fingerprint": report.fingerprint(),
            "analysis_fingerprint": analysis.fingerprint(),
            "hypothesis_id": proposal.hypothesis_id,
            "hypothesis_fingerprint": proposal.hypothesis_fingerprint,
            "extraction_method": EXTRACTION_METHOD,
            "extraction_version": EXTRACTION_VERSION,
        },
        status=ContextStatus.CANDIDATE,
        version="v1",
    )
