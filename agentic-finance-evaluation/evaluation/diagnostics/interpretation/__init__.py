"""E2-C deterministic hypothesis interpretation engine.

Reads registered COMPLETED diagnostic results, committed predictions, and
the frozen baseline control artefact; writes one ``HypothesisUpdate`` per
interpreted prediction plus a fresh ``UncertaintySnapshot`` — all through
``DiagnosticState`` ordering rules. Assessment without ranking, inference
without Bayes, interpretation without execution.
"""

from evaluation.diagnostics.interpretation.comparison import (
    Comparison,
    compare,
)
from evaluation.diagnostics.interpretation.interpreter import interpret
from evaluation.diagnostics.interpretation.methodology import (
    CONFIDENCE_STEP_CONTRADICTS,
    CONFIDENCE_STEP_INCONCLUSIVE,
    CONFIDENCE_STEP_SUPPORTS,
    METHOD,
    OPEN_STATUSES,
    TAU,
    VERSION,
)
from evaluation.diagnostics.interpretation.summary import InterpretationRecord
from evaluation.diagnostics.interpretation.updates import (
    build_update,
    next_confidence,
    next_status,
)

__all__ = [
    "Comparison",
    "compare",
    "interpret",
    "CONFIDENCE_STEP_CONTRADICTS",
    "CONFIDENCE_STEP_INCONCLUSIVE",
    "CONFIDENCE_STEP_SUPPORTS",
    "METHOD",
    "OPEN_STATUSES",
    "TAU",
    "VERSION",
    "InterpretationRecord",
    "build_update",
    "next_confidence",
    "next_status",
]
