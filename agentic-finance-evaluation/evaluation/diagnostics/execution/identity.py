"""Deterministic execution identity for diagnostic runs (E2-B).

Identity is a pure function of semantic inputs, computed with the
repository's canonical fingerprint primitive
(``evaluation.contracts.fingerprints``). No wall-clock time, UUIDs,
process/thread ids, memory addresses, or filesystem-generated values
enter any identity:

* ``episode_id`` derives from ``(diagnostic_id, test_id, seed)``;
* ``execution_fingerprint`` is the SHA-256 of the canonical form of every
  semantic input that can alter execution: diagnostic and test identity,
  test and intervention fingerprints, the requested episode configuration
  (window, universe, seed — but NOT ``base_dir``, which is a
  machine-specific path whose content identity is already carried by the
  market fingerprint, mirroring ``Trajectory.content_digest``), the
  target-agent identity/version, and the baseline reference;
* ``result_id`` derives from the execution fingerprint.

Same semantic inputs yield the same fingerprint; any semantic change
(test, intervention, environment configuration, seed, episode identity,
agent identity/version, execution configuration) changes it.
"""

from __future__ import annotations

from typing import Any, Mapping

from evaluation.contracts.fingerprints import fingerprint_of_dict


def _require_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string")
    if ":" in value and field_name in ("diagnostic_id", "test_id"):
        raise ValueError(
            f"{field_name} must not contain ':' (episode id separator)"
        )
    return value


def episode_id(diagnostic_id: str, test_id: str, seed: int) -> str:
    """Derive the deterministic diagnostic episode identity."""
    _require_id(diagnostic_id, "diagnostic_id")
    _require_id(test_id, "test_id")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {seed!r}")
    return f"{diagnostic_id}:{test_id}:seed-{seed}"


def execution_fingerprint(
    *,
    diagnostic_id: str,
    test_id: str,
    test_fingerprint: str,
    intervention_fingerprint: str,
    episode_config_identity: Mapping[str, Any],
    agent_id: str,
    agent_version: str,
    baseline_evaluation_id: str,
    baseline_fingerprint: str,
    episode_id_value: str,
) -> str:
    """Compute the deterministic execution fingerprint.

    Every parameter is a semantic input to the execution; ``base_dir`` is
    deliberately absent (provenance only, not identity).
    """
    for field_name, value in (
        ("diagnostic_id", diagnostic_id),
        ("test_id", test_id),
        ("test_fingerprint", test_fingerprint),
        ("intervention_fingerprint", intervention_fingerprint),
        ("agent_id", agent_id),
        ("agent_version", agent_version),
        ("baseline_evaluation_id", baseline_evaluation_id),
        ("baseline_fingerprint", baseline_fingerprint),
        ("episode_id_value", episode_id_value),
    ):
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{field_name} must be a non-empty string")
    if not isinstance(episode_config_identity, Mapping):
        raise TypeError("episode_config_identity must be a mapping")
    return fingerprint_of_dict(
        {
            "diagnostic_id": diagnostic_id,
            "test_id": test_id,
            "test_fingerprint": test_fingerprint,
            "intervention_fingerprint": intervention_fingerprint,
            "episode_config": dict(episode_config_identity),
            "agent_id": agent_id,
            "agent_version": agent_version,
            "baseline_evaluation_id": baseline_evaluation_id,
            "baseline_fingerprint": baseline_fingerprint,
            "episode_id": episode_id_value,
        }
    )


def result_id_for(execution_fingerprint_value: str) -> str:
    """Derive the deterministic result id from an execution fingerprint."""
    if (
        not isinstance(execution_fingerprint_value, str)
        or not execution_fingerprint_value.strip()
    ):
        raise TypeError("execution fingerprint must be a non-empty string")
    return f"R-{execution_fingerprint_value[:16]}"
