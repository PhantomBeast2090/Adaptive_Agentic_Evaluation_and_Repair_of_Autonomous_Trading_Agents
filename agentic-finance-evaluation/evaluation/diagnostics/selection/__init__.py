"""E2-D deterministic adaptive diagnostic test selection.

Reads the current ``DiagnosticState`` and prefers one eligible candidate
test under adaptive-discrimination v1. Records an auditable
``SelectionRationale`` and ``DiagnosticProposal``; executes nothing,
interprets nothing, ranks no hypotheses.
"""

from evaluation.diagnostics.selection.candidates import (
    CandidateStatistics,
    EligibilityVerdict,
    candidate_statistics,
    eligible_candidates,
    open_hypothesis_ids,
)
from evaluation.diagnostics.selection.methodology import METHOD, VERSION
from evaluation.diagnostics.selection.results import NoCandidateResult
from evaluation.diagnostics.selection.selector import select_next_test

__all__ = [
    "CandidateStatistics",
    "EligibilityVerdict",
    "candidate_statistics",
    "eligible_candidates",
    "open_hypothesis_ids",
    "METHOD",
    "VERSION",
    "NoCandidateResult",
    "select_next_test",
]
