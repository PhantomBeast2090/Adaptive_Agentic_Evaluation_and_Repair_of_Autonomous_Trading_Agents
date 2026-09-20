"""Repair outcome decision and end-to-end driver (E2-F).

``RepairDecision`` is an E2-F-local vocabulary (ACCEPTED / REJECTED /
UNRESOLVED / FAILED) that keeps repair *execution* failure distinct from
scientific *rejection*. It does not extend the frozen stopping enums.

``RepairResult`` is the frozen terminal artefact of one repair attempt,
and ``run_repair`` is the single deterministic driver composing the
frozen milestones in order:

    provider.propose → apply_repair → run_validation →
    analyze_regression → decide → anchor provenance → RepairResult

Provisional v1 decision policy (documented, not calibrated):

* UNRESOLVED when the target metric is undefined on either side;
* REJECTED when the target did not strictly improve in the requested
  direction on the diagnostic window, or regressed on the held-out
  window, or any validity count moved from zero to positive on either
  window, or any supplied tolerance tripped;
* ACCEPTED otherwise, including an explicit degenerate-activity
  guard: a candidate at inactivity 1.0 against a trading reference is
  REJECTED (permanent inactivity is not a repair). Return trade-offs
  are recorded in the findings but not adjudicated — v1 has no
  calibrated basis for them.
* FAILED only for provider, application, or validation exceptions.

Every clause above is explicit and versioned; none of it claims
calibrated scientific thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.baseline.results import BaselineResult
from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.accounting import (
    ADMISSION_RECORD_KIND,
    COMPLETED_OUTCOME,
    PARTIAL_OUTCOME,
    RepairBudgetLedger,
    admission_marker_id,
)
from evaluation.diagnostics.repair.application import (
    ApplicationStatus,
    apply_repair,
)
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.provider import (
    DeterministicRuleProvider,
    RepairProvider,
)
from evaluation.diagnostics.repair.regression import (
    RegressionAnalysis,
    ToleranceRule,
    analyze_regression,
)
from evaluation.diagnostics.repair.validation import (
    ValidationPartialFailure,
    ValidationReport,
    run_validation,
)

DECISION_METHOD = "provisional-direction-dominance"
DECISION_VERSION = "v1"

# Validity counts where a zero-to-positive move is a crisp violation
# signal requiring no calibrated threshold.
VALIDITY_COUNTS = (
    "invalid_order_count",
    "universe_violation_count",
    "no_price_count",
    "calendar_gate_count",
)

RETURN_METRIC = "cumulative_return"


class RepairDecision(str, Enum):
    """Closed local vocabulary for repair outcomes."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "RepairDecision":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(
            f"unknown RepairDecision {value!r}; known: {known}"
        )


@dataclass(frozen=True)
class RepairResult:
    """Frozen terminal record of one repair attempt."""

    repair_id: str
    proposal_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    validation_fingerprint: str
    analysis_fingerprint: str
    decision: RepairDecision = RepairDecision.UNRESOLVED
    reason: str = ""
    suggested_stopping: Optional[StoppingReason] = None
    method: str = ""
    method_version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "repair_id",
            "proposal_fingerprint",
            "candidate_id",
            "candidate_fingerprint",
            "validation_fingerprint",
            "analysis_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        decision = self.decision
        if isinstance(decision, str) and not isinstance(
            decision, RepairDecision
        ):
            decision = RepairDecision.from_str(decision)
        if not isinstance(decision, RepairDecision):
            raise TypeError(
                "decision must be a RepairDecision member, "
                f"got {self.decision!r}"
            )
        object.__setattr__(self, "decision", decision)
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        if self.suggested_stopping is not None and not isinstance(
            self.suggested_stopping, StoppingReason
        ):
            raise TypeError(
                "suggested_stopping must be a StoppingReason or None, "
                f"got {self.suggested_stopping!r}"
            )
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repair_id": self.repair_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "candidate_id": self.candidate_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "validation_fingerprint": self.validation_fingerprint,
            "analysis_fingerprint": self.analysis_fingerprint,
            "decision": self.decision.value,
            "reason": self.reason,
            "suggested_stopping": (
                self.suggested_stopping.value
                if self.suggested_stopping is not None
                else None
            ),
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairResult":
        if not isinstance(payload, Mapping):
            raise TypeError("RepairResult payload must be a mapping")
        known = {
            "repair_id", "proposal_fingerprint", "candidate_id",
            "candidate_fingerprint", "validation_fingerprint",
            "analysis_fingerprint", "decision", "reason",
            "suggested_stopping", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RepairResult fields: {sorted(extra)}"
            )
        try:
            suggested = payload.get("suggested_stopping")
            return cls(
                repair_id=payload["repair_id"],
                proposal_fingerprint=payload["proposal_fingerprint"],
                candidate_id=payload["candidate_id"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                validation_fingerprint=payload["validation_fingerprint"],
                analysis_fingerprint=payload["analysis_fingerprint"],
                decision=payload.get("decision", "UNRESOLVED"),
                reason=payload["reason"],
                suggested_stopping=(
                    StoppingReason.from_str(suggested)
                    if suggested is not None
                    else None
                ),
                method=payload["method"],
                method_version=payload.get("version", ""),
            )
        except KeyError as exc:
            raise ValueError(
                f"RepairResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def _improved(
    value: Optional[float], reference: Optional[float],
    direction: ExpectedDirection,
) -> Optional[bool]:
    if value is None or reference is None:
        return None
    if direction is ExpectedDirection.DECREASE:
        return value < reference
    return value > reference


def _decide(
    *,
    report,  # ValidationReport
    analysis: RegressionAnalysis,
    target_metric: str,
    target_direction: ExpectedDirection,
) -> Tuple[RepairDecision, str]:
    diag_target = analysis.finding(target_metric, "candidate_diagnostic")
    held_target = analysis.finding(target_metric, "candidate_heldout")
    if diag_target.reference_value is None:
        return (
            RepairDecision.UNRESOLVED,
            "target metric undefined in the diagnostic control; "
            "improvement cannot be assessed",
        )
    if diag_target.validation_value is None:
        return (
            RepairDecision.UNRESOLVED,
            "target metric undefined for the candidate on the diagnostic "
            "window; improvement cannot be assessed",
        )
    diag_better = _improved(
        diag_target.validation_value,
        diag_target.reference_value,
        target_direction,
    )
    if not diag_better:
        return (
            RepairDecision.REJECTED,
            "target metric did not strictly improve in the requested "
            "direction on the diagnostic window",
        )
    for finding in analysis.findings:
        if finding.within_tolerance is False:
            return (
                RepairDecision.REJECTED,
                f"named tolerance tripped for {finding.metric_name!r} on "
                f"{finding.window_label!r}",
            )
    for window in ("candidate_diagnostic", "candidate_heldout"):
        for name in VALIDITY_COUNTS:
            try:
                finding = analysis.finding(name, window)
            except KeyError:
                continue
            if (
                finding.reference_value == 0.0
                and finding.validation_value is not None
                and finding.validation_value > 0.0
            ):
                return (
                    RepairDecision.REJECTED,
                    f"new constraint violations: {name!r} moved from zero "
                    f"on {window!r}",
                )
    held_better = _improved(
        held_target.validation_value,
        held_target.reference_value,
        target_direction,
    )
    if held_better is None:
        return (
            RepairDecision.UNRESOLVED,
            "target metric undefined on the held-out comparison; "
            "generalisation cannot be assessed",
        )
    if not held_better:
        return (
            RepairDecision.REJECTED,
            "target improvement did not generalise to the held-out window",
        )
    for window in ("candidate_diagnostic", "candidate_heldout"):
        try:
            inactivity = analysis.finding("inactivity_rate", window)
        except KeyError:
            continue
        if (
            inactivity.validation_value == 1.0
            and inactivity.reference_value is not None
            and inactivity.reference_value < 1.0
        ):
            return (
                RepairDecision.REJECTED,
                "candidate ceased all trading activity on "
                f"{window!r} while the reference traded: permanent "
                "inactivity is not a repair",
            )
    return (
        RepairDecision.ACCEPTED,
        "target improved on the diagnostic window and held out, with "
        "no new violations, no tripped tolerances, and no cessation "
        "of trading (provisional v1 policy: return trade-offs are "
        "recorded, not adjudicated)",
    )


def run_repair(
    *,
    diagnostic_state: DiagnosticState,
    baseline: BaselineResult,
    original_agent: Any,
    hypothesis_id: str,
    heldout_window: Tuple[str, str],
    seed: Optional[int] = None,
    provider: RepairProvider | None = None,
    tolerances: Tuple[ToleranceRule, ...] = (),
    base_dir: str = ".",
) -> Tuple[RepairResult, Any, Any, Any]:
    """Run one complete repair attempt: propose, apply, validate, decide.

    Returns ``(result, validation_report, analysis, live_candidate)``
    where the live candidate is ``None`` when application failed. The
    original agent and all input artefacts are never mutated; repair and
    validation provenance is anchored on the diagnostic state's E0
    evaluation state via its existing note slots.

    Budget ownership: one admitted attempt consumes exactly 1 repair unit
    before provider/application/validation work (all outcomes consume; no
    rollback); one complete validation consumes exactly 3 validation-run
    units, and validation never starts with fewer than 3 remaining.
    Refused attempts append nothing and invoke nothing. Usage is derived
    from the persisted E0 slots via ``RepairBudgetLedger`` — return shapes
    are unchanged.
    """
    if not isinstance(diagnostic_state, DiagnosticState):
        raise TypeError(
            "diagnostic_state must be a DiagnosticState, "
            f"got {type(diagnostic_state).__name__}"
        )
    if not isinstance(baseline, BaselineResult):
        raise TypeError(
            "baseline must be a BaselineResult, "
            f"got {type(baseline).__name__}"
        )
    if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
        raise ValueError("hypothesis_id must be a non-empty string")
    provider = provider or DeterministicRuleProvider()
    hypothesis = diagnostic_state.hypothesis(hypothesis_id)
    budget = diagnostic_state.budget
    ledger = RepairBudgetLedger.from_evaluation_state(
        diagnostic_state.evaluation_state
    )
    if budget.is_exhausted({"repairs": ledger.repairs_used}):
        raise ValueError(
            "repair budget exhausted before proposal: "
            f"{ledger.repairs_used} repair units already consumed"
        )
    remaining_runs = budget.remaining(
        {"validation_runs": ledger.validation_runs_used}
    ).get("validation_runs")
    if remaining_runs is not None and remaining_runs < 3:
        raise ValueError(
            "validation budget cannot cover the three fixed comparison "
            f"runs (remaining: {remaining_runs})"
        )
    repair_id = (
        f"repair-{diagnostic_state.diagnostic_id}-{hypothesis_id}"
    )
    # Admission consumes exactly 1 repair unit BEFORE provider, application,
    # or validation work. Every admitted outcome — success, rejection,
    # or any failure — therefore consumes; refused attempts append nothing.
    # The marker uses the @admission namespace, disjoint from
    # applied-candidate identifiers, and is always followed by the real
    # provenance note, so existing [-1] provenance reads are unaffected.
    diagnostic_state.evaluation_state.note_repair_candidate(
        {
            "candidate_id": admission_marker_id(repair_id),
            "repair_id": repair_id,
            "diagnostic_id": diagnostic_state.diagnostic_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "record_kind": ADMISSION_RECORD_KIND,
        }
    )
    try:
        return _attempt_repair(
            diagnostic_state=diagnostic_state,
            baseline=baseline,
            original_agent=original_agent,
            hypothesis=hypothesis,
            repair_id=repair_id,
            heldout_window=heldout_window,
            seed=seed,
            provider=provider,
            tolerances=tolerances,
            base_dir=base_dir,
        )
    except Exception as exc:
        agent_identity = original_agent.identity
        return (
            RepairResult(
                repair_id=repair_id,
                proposal_fingerprint="none",
                candidate_id=(
                    f"{agent_identity.agent_id}@candidate-unproposed"
                ),
                candidate_fingerprint="none",
                validation_fingerprint="none",
                analysis_fingerprint="none",
                decision=RepairDecision.FAILED,
                reason=(
                    f"repair failed before application: "
                    f"{type(exc).__name__}: {exc}"
                ),
                suggested_stopping=StoppingReason.REPAIR_FAILED,
                method=provider.method,
                method_version=provider.version,
            ),
            None,
            None,
            None,
        )


def _attempt_repair(
    *,
    diagnostic_state: DiagnosticState,
    baseline: BaselineResult,
    original_agent: Any,
    hypothesis: Any,
    repair_id: str,
    heldout_window: Tuple[str, str],
    seed: Optional[int],
    provider: RepairProvider,
    tolerances: Tuple[ToleranceRule, ...],
    base_dir: str,
) -> Tuple[RepairResult, Any, Any, Any]:
    try:
        from evaluation.diagnostics.repair.application import (
            fingerprint_agent,
        )

        live_fp = fingerprint_agent(
            original_agent, original_agent.identity
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"original agent is not a fingerprintable repair target: {exc}"
        ) from exc
    proposal = provider.propose(
        repair_id=repair_id,
        diagnostic_id=diagnostic_state.diagnostic_id,
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        diagnostic_state_fingerprint=diagnostic_state.fingerprint(),
        target_agent_identity=original_agent.identity,
        target_agent_fingerprint=live_fp,
        hypothesis_id=hypothesis.hypothesis_id,
        hypothesis_fingerprint=hypothesis.fingerprint(),
        failure_class=hypothesis.failure_class,
        evidence_refs=tuple(hypothesis.evidence_refs),
    )
    candidate, application, live_candidate = apply_repair(
        proposal, original_agent,
        provider_name=type(provider).__name__,
    )
    diagnostic_state.evaluation_state.note_repair_candidate(
        {
            "candidate_id": candidate.candidate_id,
            "proposal_fingerprint": proposal.fingerprint(),
            "candidate_fingerprint": candidate.candidate_fingerprint,
            "application_fingerprint": application.fingerprint(),
            "application_status": application.status.value,
        }
    )
    if (
        application.status is not ApplicationStatus.APPLIED
        or live_candidate is None
    ):
        result = RepairResult(
            repair_id=repair_id,
            proposal_fingerprint=proposal.fingerprint(),
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.candidate_fingerprint,
            validation_fingerprint="none",
            analysis_fingerprint="none",
            decision=RepairDecision.FAILED,
            reason=(
                f"repair application failed: {application.error}"
            ),
            suggested_stopping=StoppingReason.REPAIR_FAILED,
            method=proposal.method,
            method_version=proposal.method_version,
        )
        return result, None, None, None
    try:
        report, _artefacts = run_validation(
            validation_id=f"validation-{repair_id}",
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.candidate_fingerprint,
            candidate_agent=live_candidate,
            original_agent=original_agent,
            baseline=baseline,
            heldout_window=heldout_window,
            seed=seed,
            base_dir=base_dir,
        )
    except ValidationPartialFailure as exc:
        # Invoked runs consumed execution: record exactly runs_invoked
        # units with no rollback, then fail explicitly. Validation never
        # started zero runs here would mean no note at all.
        diagnostic_state.evaluation_state.note_validation_result(
            {
                "candidate_id": candidate.candidate_id,
                "repair_id": repair_id,
                "validation_runs_consumed": exc.runs_invoked,
                "outcome": PARTIAL_OUTCOME,
                "failed_label": exc.label,
                "decision": RepairDecision.FAILED.value,
            }
        )
        result = RepairResult(
            repair_id=repair_id,
            proposal_fingerprint=proposal.fingerprint(),
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.candidate_fingerprint,
            validation_fingerprint="none",
            analysis_fingerprint="none",
            decision=RepairDecision.FAILED,
            reason=(
                f"validation failed after {exc.runs_invoked} of 3 runs "
                f"at {exc.label!r}: {exc.error} "
                "(consumed runs are not rolled back)"
            ),
            suggested_stopping=StoppingReason.REPAIR_FAILED,
            method=proposal.method,
            method_version=proposal.method_version,
        )
        return result, None, None, None
    baseline_metrics = {
        metric.name: metric.value for metric in baseline.metrics
    }
    comparisons = []
    for run in report.runs:
        if run.label == "candidate_diagnostic":
            reference = baseline_metrics
        elif run.label == "candidate_heldout":
            reference = dict(
                report.run("original_heldout").metrics
            )
        else:
            continue
        for name, value in dict(run.metrics).items():
            comparisons.append(
                (run.label, name, reference.get(name), value)
            )
    analysis = analyze_regression(
        analysis_id=f"analysis-{repair_id}",
        candidate_id=candidate.candidate_id,
        validation_fingerprint=report.fingerprint(),
        comparisons=tuple(comparisons),
        tolerances=tolerances,
    )
    decision, reason = _decide(
        report=report,
        analysis=analysis,
        target_metric=proposal.target_metric,
        target_direction=proposal.target_direction,
    )
    diagnostic_state.evaluation_state.note_validation_result(
        {
            "candidate_id": candidate.candidate_id,
            "repair_id": repair_id,
            "validation_runs_consumed": 3,
            "outcome": COMPLETED_OUTCOME,
            "validation_fingerprint": report.fingerprint(),
            "analysis_fingerprint": analysis.fingerprint(),
            "decision": decision.value,
        }
    )
    result = RepairResult(
        repair_id=repair_id,
        proposal_fingerprint=proposal.fingerprint(),
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        validation_fingerprint=report.fingerprint(),
        analysis_fingerprint=analysis.fingerprint(),
        decision=decision,
        reason=reason,
        suggested_stopping=None,
        method=proposal.method,
        method_version=proposal.method_version,
    )
    return result, report, analysis, live_candidate
