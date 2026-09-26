"""Diagnostic translation layer.

Re-exports the frozen ``FailureHypothesis`` contract (moved into this
package verbatim; existing ``from evaluation.ml.diagnosis import
FailureHypothesis`` imports resolve unchanged) alongside the new
forecast-diagnostic join, conditional miner, extended hypothesis
schema, and builder.
"""

from evaluation.ml.diagnosis.hypothesis import FailureHypothesis
from evaluation.ml.diagnosis.failure_hypothesis import (
    CANDIDATE, DiagnosticHypothesis,
)
from evaluation.ml.diagnosis import forecast_diagnostics
from evaluation.ml.diagnosis import conditional_miner
from evaluation.ml.diagnosis import hypothesis_builder

__all__ = ["CANDIDATE", "DiagnosticHypothesis", "FailureHypothesis",
           "conditional_miner", "forecast_diagnostics",
           "hypothesis_builder"]
