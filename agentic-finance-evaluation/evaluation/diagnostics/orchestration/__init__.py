"""E2-E closed-loop diagnostic orchestration.

Reads a ``DiagnosticState`` and drives the frozen milestones in a
deterministic loop — E2-D selects, E2-B executes, E2-C interprets —
until an explicit terminal condition. The controller owns no evaluation
logic, keeps no shadow state, and performs no repair.
"""

from evaluation.diagnostics.orchestration.config import OrchestrationConfig
from evaluation.diagnostics.orchestration.controller import run
from evaluation.diagnostics.orchestration.results import OrchestrationResult
from evaluation.diagnostics.orchestration.stopping import (
    METHOD,
    TERMINAL_MAPPING,
    VERSION,
)
from evaluation.diagnostics.orchestration.trace import IterationTraceEntry

__all__ = [
    "OrchestrationConfig",
    "run",
    "OrchestrationResult",
    "METHOD",
    "TERMINAL_MAPPING",
    "VERSION",
    "IterationTraceEntry",
]
