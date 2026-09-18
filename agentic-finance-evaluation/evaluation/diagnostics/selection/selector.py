"""Deterministic adaptive diagnostic test selection (E2-D).

:func:`select_next_test` reads the current ``DiagnosticState`` and returns
either a recorded ``DiagnosticProposal`` (with its ``SelectionRationale``)
or a frozen ``NoCandidateResult``. It executes nothing, interprets
nothing, ranks no hypotheses, and computes no probabilities: it orders
eligible candidate tests by the lexicographic key ``(-D, -C, cost,
test_id)`` — rival-pair discrimination, open-hypothesis coverage,
estimated cost, stable id tie-break — and prefers the first candidate
under adaptive-discrimination v1.

Because every input (open set, committed predictions, executed tests,
budget, stopping state) is read from current state, the preferred
candidate changes as diagnostic evidence changes the state. That
state-conditioning is the whole of E2-D's adaptivity claim.
"""

from __future__ import annotations

from typing import Tuple, Union

from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.proposals import (
    CandidateAssessment,
    DiagnosticProposal,
    SelectionRationale,
)
from evaluation.diagnostics.selection.candidates import (
    CandidateStatistics,
    candidate_statistics,
    eligible_candidates,
    open_hypothesis_ids,
)
from evaluation.diagnostics.selection.methodology import (
    DISCRIMINATION_TEMPLATE,
    METHOD,
    NO_SEPARATION_PREFIX,
    VERSION,
)
from evaluation.diagnostics.selection.results import NoCandidateResult


def _content_id(
    prefix: str,
    diagnostic_id: str,
    selected: str,
    ordered_ids: Tuple[str, ...],
    state_fingerprint: str,
) -> str:
    return prefix + fingerprint_of_dict(
        {
            "diagnostic_id": diagnostic_id,
            "selected_test_id": selected,
            "candidate_ids": list(ordered_ids),
            "method": METHOD,
            "version": VERSION,
            "state_fingerprint": state_fingerprint,
        }
    )[:16]


def _describe(stats: CandidateStatistics, fallback: bool) -> str:
    text = DISCRIMINATION_TEMPLATE.format(
        pairs=stats.discrimination_pairs,
        coverage=stats.open_coverage,
        cost=stats.estimated_cost,
    )
    if fallback:
        text = NO_SEPARATION_PREFIX + text
    return text


def _proposal_confidence(
    stats: CandidateStatistics, total_open: int
) -> float:
    """Structural selection confidence for the preferred candidate.

    It measures structural support for the selected diagnostic test
    under the selection policy. It is not confidence that any
    hypothesis is true, not a probability, and not a posterior.
    Complete coverage without rival discrimination yields 0.0:
    covering every open hypothesis says nothing about separating them.
    """
    if total_open <= 0:
        return 0.0
    if stats.discrimination_pairs == 0:
        return 0.0
    if stats.open_coverage >= total_open:
        return 1.0
    return min(1.0, max(0.0, stats.open_coverage / total_open))


def select_next_test(
    state: DiagnosticState,
) -> Union[DiagnosticProposal, NoCandidateResult]:
    """Prefer one eligible candidate test under the current state.

    ``select_next_test`` is deterministic and state-conditioned — not a
    pure function: on success it records the rationale and proposal in
    ``state``. Terminal conditions yield a frozen ``NoCandidateResult`` (never an exception,
    never a silent default); only wrong-type callers raise ``TypeError``.
    Stopping state is read, never written; budget counts are read, never
    consumed (a proposal is not an execution).
    """
    if not isinstance(state, DiagnosticState):
        raise TypeError(
            "state must be a DiagnosticState, "
            f"got {type(state).__name__}"
        )
    if state.stopping_reason is not None:
        return NoCandidateResult(
            diagnostic_id=state.diagnostic_id,
            reason=(
                "diagnostic already stopped: "
                f"{state.stopping_reason.value}; no new proposal created"
            ),
            suggested_stopping=state.stopping_reason,
            candidates_considered=0,
            method=METHOD,
            version=VERSION,
        )
    if state.budget_exhausted():
        return NoCandidateResult(
            diagnostic_id=state.diagnostic_id,
            reason=(
                "diagnostic test budget exhausted; "
                "proposal formation refused"
            ),
            suggested_stopping=StoppingReason.BUDGET_EXHAUSTED,
            candidates_considered=len(state.available_tests),
            method=METHOD,
            version=VERSION,
        )
    eligible, _verdicts = eligible_candidates(state)
    if not eligible:
        open_ids = open_hypothesis_ids(state)
        if not open_ids:
            return NoCandidateResult(
                diagnostic_id=state.diagnostic_id,
                reason="no open hypotheses remain to discriminate",
                suggested_stopping=StoppingReason.NO_ACTIONABLE_FAILURE,
                candidates_considered=len(state.available_tests),
                method=METHOD,
                version=VERSION,
            )
        return NoCandidateResult(
            diagnostic_id=state.diagnostic_id,
            reason=(
                "no registered test is eligible: every candidate is "
                "executed, budget-blocked, or lacks a committed prediction "
                "for an open hypothesis"
            ),
            suggested_stopping=StoppingReason.HYPOTHESIS_UNRESOLVED,
            candidates_considered=len(state.available_tests),
            method=METHOD,
            version=VERSION,
        )

    stats = [candidate_statistics(state, test) for test in eligible]
    ordered = sorted(stats, key=lambda s: s.selection_key())
    selected = ordered[0]
    fallback = all(s.discrimination_pairs == 0 for s in ordered)

    assessments = [
        CandidateAssessment(
            test_id=s.test_id,
            expected_discrimination=_describe(s, fallback),
            estimated_cost=s.estimated_cost,
        )
        for s in ordered
    ]
    ordered_ids = tuple(s.test_id for s in ordered)
    rationale = SelectionRationale(
        rationale_id=_content_id(
            "rat-",
            state.diagnostic_id,
            selected.test_id,
            ordered_ids,
            state.fingerprint(),
        ),
        candidates=tuple(assessments),
        selected_test_id=selected.test_id,
        selection_score=None,
        method=METHOD,
        version=VERSION,
    )
    state.record_rationale(rationale)

    open_predictions = [
        p
        for p in state.predictions
        if p.test_id == selected.test_id
        and p.hypothesis_id in set(open_hypothesis_ids(state))
    ]
    hypothesis_ids = tuple(
        sorted({p.hypothesis_id for p in open_predictions})
    )
    prediction_ids = tuple(sorted(p.prediction_id for p in open_predictions))
    proposal = DiagnosticProposal(
        proposal_id=_content_id(
            "prop-",
            state.diagnostic_id,
            selected.test_id,
            ordered_ids,
            state.fingerprint(),
        ),
        hypothesis_ids=hypothesis_ids,
        prediction_ids=prediction_ids,
        selected_test_id=selected.test_id,
        expected_discrimination=_describe(selected, fallback),
        rationale_id=rationale.rationale_id,
        confidence=_proposal_confidence(
            selected, len(open_hypothesis_ids(state))
        ),
        alternative_test_ids=tuple(
            s.test_id for s in ordered[1:]
        ),
        method=METHOD,
        version=VERSION,
    )
    state.record_proposal(proposal)
    return proposal
