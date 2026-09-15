"""E2-A diagnostic contracts: representations for the adaptive loop.

This package establishes the deterministic contracts on which the future
diagnostic runner and selector (E2-B) will be built. It contains
representations only: no LLM, no selector algorithm, no executor, no
inference, no repair, no learning.

Contracts (all frozen dataclasses except the accumulator):

* ``predictions`` — committed falsifiable claims (``HypothesisPrediction``).
* ``test_results`` — observed execution records (``DiagnosticTestResult``).
* ``hypothesis_updates`` — assessed encounters (``HypothesisUpdate``).
* ``diagnostic_state`` — append-only working memory (``DiagnosticState``)
  plus the minimal uncertainty snapshot (``UncertaintySnapshot``).
* ``proposals`` — selector output shape (``DiagnosticProposal``,
  ``SelectionRationale``, ``CandidateAssessment``).

Reused unchanged from frozen layers: E0 ``Hypothesis``,
``DiagnosticTest``, ``EvaluationState``, ``EvaluationBudget``,
``StoppingReason``, ``TargetObservation``/``OraclePacket`` semantics, and
E1 ``MetricResult`` for measured outcomes.
"""

from evaluation.diagnostics.contracts.diagnostic_state import (
    DiagnosticState,
    UncertaintySnapshot,
)
from evaluation.diagnostics.contracts.hypothesis_updates import (
    Compatibility,
    HypothesisUpdate,
)
from evaluation.diagnostics.contracts.predictions import (
    ExpectedDirection,
    HypothesisPrediction,
)
from evaluation.diagnostics.contracts.proposals import (
    CandidateAssessment,
    DiagnosticProposal,
    SelectionRationale,
)
from evaluation.diagnostics.contracts.test_results import (
    DiagnosticExecutionStatus,
    DiagnosticTestResult,
)

__all__ = [
    "DiagnosticState",
    "UncertaintySnapshot",
    "Compatibility",
    "HypothesisUpdate",
    "ExpectedDirection",
    "HypothesisPrediction",
    "CandidateAssessment",
    "DiagnosticProposal",
    "SelectionRationale",
    "DiagnosticExecutionStatus",
    "DiagnosticTestResult",
]
