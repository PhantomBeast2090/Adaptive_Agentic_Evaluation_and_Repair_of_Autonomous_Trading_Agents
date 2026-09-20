"""Deterministic experiment identity (orchestration only, no science).

``experiment_identity`` is SHA-256 over canonical JSON built exclusively
from frozen scientific inputs. Time-of-day clocks, run identifiers,
process identifiers, machine names, and random entropy can never enter:
and random entropy can never enter: they are not parameters at all, so
no code path can smuggle them in. Seeds travel as provenance fields.
Identical configuration always yields identical identity.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict

from evaluation.contracts.fingerprints import fingerprint_of_dict
from experiments.harness.config import ExperimentConfig

IDENTITY_METHOD = "e3e-experiment-identity"
IDENTITY_VERSION = "v1"

EXECUTION_METHOD = "e3e-execution-identity"
EXECUTION_VERSION = "v1"


class ExecutionRole(str, Enum):
    """Closed vocabulary for execution purpose (orchestration, no science).

    The role never enters scientific identity. It distinguishes what an
    execution *was for* so validation, primary, and reproduction
    artefacts can never collide or masquerade as one another.
    """

    SYSTEM_VALIDATION = "SYSTEM_VALIDATION"
    TIER1_PRIMARY = "TIER1_PRIMARY"
    REPRODUCTION = "REPRODUCTION"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "ExecutionRole":
        for member in cls:
            if value == member.value:
                return member
        raise ValueError(f"unknown ExecutionRole {value!r}")


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
    """Deterministic artefact path for one experiment result.

    Legacy layout (no execution role). Historical artefacts remain
    readable through this path; new executions must use
    :func:`execution_result_path`.
    """
    if not isinstance(result_dir, str) or not result_dir.strip():
        raise ValueError("result_dir must be a non-empty string")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    return f"{result_dir.rstrip('/')}/{experiment_id}.json"


def _require_instance(instance: str) -> str:
    if not isinstance(instance, str) or not instance.strip():
        raise ValueError(
            "execution_instance must be a non-empty string, "
            "e.g. '001': repeated executions are explicit, never silent"
        )
    if "/" in instance or instance in (".", ".."):
        raise ValueError(
            f"execution_instance {instance!r} must be a plain label"
        )
    return instance


def execution_id(
    experiment_id: str, role: ExecutionRole | str, instance: str
) -> str:
    """Deterministic execution identity: scientific id + role + instance.

    Scientific identity is an input, never an ingredient that changes:
    the same configuration always yields the same experiment_id, while
    distinct (role, instance) pairs yield distinct, non-colliding
    execution ids. No timestamps, run identifiers, process identifiers,
    enter: all three inputs are explicit operator-supplied values.
    """
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    if isinstance(role, str) and not isinstance(role, ExecutionRole):
        role = ExecutionRole.from_str(role)
    if not isinstance(role, ExecutionRole):
        raise TypeError(
            f"role must be an ExecutionRole, got {role!r}"
        )
    return fingerprint_of_dict(
        {
            "method": EXECUTION_METHOD,
            "version": EXECUTION_VERSION,
            "experiment_id": experiment_id,
            "role": role.value,
            "instance": _require_instance(instance),
        }
    )


def execution_result_path(
    result_dir: str, experiment_id: str, execution_id_value: str
) -> str:
    """Deterministic artefact path for one execution instance.

    Layout ``results/e3/<experiment_id>/<execution_id>.json``: the same
    scientific configuration under different roles/instances can never
    share a path, so no execution can silently overwrite another.
    """
    if not isinstance(result_dir, str) or not result_dir.strip():
        raise ValueError("result_dir must be a non-empty string")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    if not isinstance(execution_id_value, str) or not (
        execution_id_value.strip()
    ):
        raise ValueError("execution_id must be a non-empty string")
    return (
        f"{result_dir.rstrip('/')}/{experiment_id}/"
        f"{execution_id_value}.json"
    )
