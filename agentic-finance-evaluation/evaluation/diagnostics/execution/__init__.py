"""E2-B deterministic diagnostic intervention and execution engine.

Runs a registered ``DiagnosticTest`` with committed predictions in an
isolated diagnostic episode: materialises the intervention into a fresh
environment, drives the target agent through the E0 invocation boundary,
records episode-owned ``DecisionRecord`` objects, measures the test's
named outcomes, and registers a ``DiagnosticTestResult``.

Non-adaptive by design: the executor runs the test it is given and
reports observations. No hypothesis judgement, no selection, no repair.
"""

from evaluation.diagnostics.execution.episode import (
    DiagnosticEpisode,
    DiagnosticEpisodeConfig,
)
from evaluation.diagnostics.execution.executor import execute
from evaluation.diagnostics.execution.identity import (
    episode_id,
    execution_fingerprint,
    result_id_for,
)
from evaluation.diagnostics.execution.interventions import (
    InvalidIntervention,
    SUPPORTED_INTERVENTION_TYPES,
    resolve_env_config,
)

__all__ = [
    "DiagnosticEpisode",
    "DiagnosticEpisodeConfig",
    "execute",
    "episode_id",
    "execution_fingerprint",
    "result_id_for",
    "InvalidIntervention",
    "SUPPORTED_INTERVENTION_TYPES",
    "resolve_env_config",
]
