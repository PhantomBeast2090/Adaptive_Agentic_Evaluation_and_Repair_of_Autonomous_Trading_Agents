"""Deterministic experiment identity (orchestration only, no science).

``experiment_identity`` is SHA-256 over canonical JSON built exclusively
from frozen scientific inputs. Time-of-day clocks, run identifiers,
process identifiers, machine names, and random entropy can never enter:
and random entropy can never enter: they are not parameters at all, so
no code path can smuggle them in. Seeds travel as provenance fields.
Identical configuration always yields identical identity.
"""

from __future__ import annotations

from typing import Any, Dict

from evaluation.contracts.fingerprints import fingerprint_of_dict
from experiments.harness.config import ExperimentConfig

IDENTITY_METHOD = "e3e-experiment-identity"
IDENTITY_VERSION = "v1"


def identity_payload(config: ExperimentConfig) -> Dict[str, Any]:
    """Canonical identity inputs for one experiment configuration."""
    if not isinstance(config, ExperimentConfig):
        raise TypeError(
            "config must be an ExperimentConfig, "
            f"got {type(config).__name__}"
        )
    return {
        "method": IDENTITY_METHOD,
        "version": IDENTITY_VERSION,
        "protocol_version": config.protocol_version,
        "e3d_fingerprint": config.e3d_fingerprint,
        "benchmark_id": config.benchmark_id,
        "benchmark_version": config.benchmark_version,
        "agent_id": config.agent_id,
        "agent_version": config.agent_version,
        "environment_fingerprint": config.environment_fingerprint,
        "dataset_fingerprints": dict(config.dataset_fingerprints),
        "calendar_fingerprint": config.calendar_fingerprint,
        "diagnostic_window": list(config.diagnostic_window),
        "heldout_window": list(config.heldout_window),
        "universe": dict(config.universe),
        "transaction_cost_bps": config.transaction_cost_bps,
        "initial_cash": config.initial_cash,
        "strict_pit": config.strict_pit,
        "vintage_policy": config.vintage_policy,
        "diagnostic_policy": config.diagnostic_policy,
        "candidate_pool": list(config.candidate_pool),
        "budgets": dict(config.budgets),
        "seed_provenance": config.seed_provenance,
        "arm": config.arm,
    }


def experiment_identity(config: ExperimentConfig) -> str:
    """Deterministic SHA-256 identity for one experiment configuration."""
    return fingerprint_of_dict(identity_payload(config))


def arm_identity(experiment_id: str, arm: str) -> str:
    """Deterministic identity for one arm within an experiment."""
    from experiments.harness.config import ARMS

    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")
    return fingerprint_of_dict(
        {
            "method": IDENTITY_METHOD,
            "version": IDENTITY_VERSION,
            "experiment_id": experiment_id,
            "arm": arm,
        }
    )


def result_path(result_dir: str, experiment_id: str) -> str:
    """Deterministic artefact path for one experiment result."""
    if not isinstance(result_dir, str) or not result_dir.strip():
        raise ValueError("result_dir must be a non-empty string")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    return f"{result_dir.rstrip('/')}/{experiment_id}.json"
