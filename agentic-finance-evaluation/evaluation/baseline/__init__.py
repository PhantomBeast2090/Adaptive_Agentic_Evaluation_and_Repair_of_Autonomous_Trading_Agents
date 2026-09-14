"""E1 deterministic baseline evaluator.

Connects the frozen Indian multi-asset environment to the frozen E0
contracts: trusted observations, agent invocation, immutable decision
records, deterministic metrics and baseline evidence, accumulated into an
E0 ``EvaluationState`` and returned as a canonical ``BaselineResult``.

Measurement only. No diagnosis, no test selection, no repair, no learning.
"""

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.evidence import (
    derive_baseline_evidence,
    evidence_metric_names,
)
from evaluation.baseline.metrics import (
    METRIC_FUNCTIONS,
    MetricResult,
    compute_all,
)
from evaluation.baseline.results import BaselineResult
from evaluation.baseline.runner import run_baseline
from evaluation.baseline.trusted import (
    observation_portfolio,
    observe_current,
    split_visibility,
)

__all__ = [
    "BaselineConfig",
    "derive_baseline_evidence",
    "evidence_metric_names",
    "METRIC_FUNCTIONS",
    "MetricResult",
    "compute_all",
    "BaselineResult",
    "run_baseline",
    "observation_portfolio",
    "observe_current",
    "split_visibility",
]
