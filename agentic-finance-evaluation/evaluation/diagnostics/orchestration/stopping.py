"""Termination mapping for the orchestration loop (E2-E).

This module holds data, not logic: the table mapping terminal loop
conditions onto the frozen E0 ``StoppingReason`` vocabulary. The
controller applies the table; nothing here decides anything.

Mapping rationale (documented once, applied uniformly):

* selector reports budget exhaustion → ``BUDGET_EXHAUSTED``;
* selector echoes an already-set reason → that reason, unchanged;
* selector reports open-but-untestable hypotheses → the selector's own
  ``HYPOTHESIS_UNRESOLVED`` suggestion is honoured;
* selector reports nothing open → ``NO_ACTIONABLE_FAILURE`` (closed
  hypotheses need no further diagnosis; this is a lifecycle mapping,
  not evidence any agent is "good");
* iteration cap reached with work remaining → ``HYPOTHESIS_UNRESOLVED``
  (the loop ended without resolution, not with success).

No new stopping vocabulary is introduced. ``SUCCESS_CONFIDENT`` is never
produced by orchestration: confidence in a diagnosis is not an E2-E
concept.
"""

from __future__ import annotations

from evaluation.contracts.stopping import StoppingReason

# Terminal condition name -> StoppingReason. Condition names are internal
# loop vocabulary; only the mapped StoppingReason ever leaves E2-E.
TERMINAL_MAPPING = {
    "budget_exhausted": StoppingReason.BUDGET_EXHAUSTED,
    "no_actionable": StoppingReason.NO_ACTIONABLE_FAILURE,
    "unresolved": StoppingReason.HYPOTHESIS_UNRESOLVED,
    "iteration_cap": StoppingReason.HYPOTHESIS_UNRESOLVED,
}

METHOD = "closed-loop-orchestration"
VERSION = "v1"
