"""Immutable experiment result artefact (orchestration only, no science).

``ExperimentResult`` assembles frozen-primitive outputs into one
serialisable, fingerprinted record. It computes no metrics, runs no
statistics, and ranks nothing: deltas are stored as recorded paired
differences, and the RQ4 status is a frozen descriptive-only enum.
Scientific identity excludes the operational block.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from experiments.harness.errors import ProvenanceError

RESULT_METHOD = "e3e-experiment-result"
RESULT_VERSION = "v1"

RQ4_DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS"

RESULT_STATES = ("SUCCESS", "INCONCLUSIVE", "REGRESSION", "INVALID", "FAILED")


class RQ4Status(str, Enum):
    """Closed vocabulary for the RQ4 output status."""

    DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS = "DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "RQ4Status":
        for member in cls:
            if value == member.value:
                return member
        raise ValueError(f"unknown RQ4Status {value!r}")


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ExperimentResult:
    """One frozen, replayable experimental result."""

    experiment_id: str
    protocol_fingerprint: str
    arm_records: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    benchmark_identity: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    agent_identity: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    environment_identity: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    configuration: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    lineage: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    metrics_nd: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    metrics_nh: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    metrics_rd: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    metrics_rh: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    delta_diagnostic: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    delta_heldout: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    rq4_vector: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    rq4_status: RQ4Status = RQ4Status.DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS
    result_state: str = "INCONCLUSIVE"
    failure_detail: str = ""
    integrity_checks: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    method: str = RESULT_METHOD
    method_version: str = RESULT_VERSION
    operational: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        _require_str(self.experiment_id, "experiment_id")
        _require_str(self.protocol_fingerprint, "protocol_fingerprint")
        for field_name in (
            "arm_records", "benchmark_identity", "agent_identity",
            "environment_identity", "configuration", "lineage",
            "metrics_nd", "metrics_nh", "metrics_rd", "metrics_rh",
            "delta_diagnostic", "delta_heldout", "rq4_vector",
            "integrity_checks", "operational",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{field_name} must be a mapping")
            object.__setattr__(self, field_name, freeze(dict(value)))
        status = self.rq4_status
        if isinstance(status, str) and not isinstance(status, RQ4Status):
            status = RQ4Status.from_str(status)
        if not isinstance(status, RQ4Status):
            raise TypeError(
                f"rq4_status must be an RQ4Status, got {status!r}"
            )
        object.__setattr__(self, "rq4_status", status)
        if self.result_state not in RESULT_STATES:
            raise ValueError(
                f"result_state must be one of {RESULT_STATES}, "
                f"got {self.result_state!r}"
            )
        if not isinstance(self.failure_detail, str):
            raise TypeError("failure_detail must be a string")
        _require_str(self.method, "method")
        _require_str(self.method_version, "method_version")
        delta_heldout = dict(self.delta_heldout)
        comparator = delta_heldout.get("baseline_original_heldout")
        repaired = delta_heldout.get("repaired_heldout")
        if delta_heldout and (comparator is None or repaired is None):
            raise ValueError(
                "delta_heldout must explicitly identify "
                "baseline_original_heldout and repaired_heldout"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_fingerprint": self.protocol_fingerprint,
            "arm_records": thaw(self.arm_records),
            "benchmark_identity": thaw(self.benchmark_identity),
            "agent_identity": thaw(self.agent_identity),
            "environment_identity": thaw(self.environment_identity),
            "configuration": thaw(self.configuration),
            "lineage": thaw(self.lineage),
            "metrics_nd": thaw(self.metrics_nd),
            "metrics_nh": thaw(self.metrics_nh),
            "metrics_rd": thaw(self.metrics_rd),
            "metrics_rh": thaw(self.metrics_rh),
            "delta_diagnostic": thaw(self.delta_diagnostic),
            "delta_heldout": thaw(self.delta_heldout),
            "rq4_vector": thaw(self.rq4_vector),
            "rq4_status": self.rq4_status.value,
            "result_state": self.result_state,
            "failure_detail": self.failure_detail,
            "integrity_checks": thaw(self.integrity_checks),
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentResult":
        if not isinstance(payload, Mapping):
            raise TypeError("ExperimentResult payload must be a mapping")
        known = {
            "experiment_id", "protocol_fingerprint", "arm_records",
            "benchmark_identity", "agent_identity",
            "environment_identity", "configuration", "lineage",
            "metrics_nd", "metrics_nh", "metrics_rd", "metrics_rh",
            "delta_diagnostic", "delta_heldout", "rq4_vector",
            "rq4_status", "result_state", "failure_detail",
            "integrity_checks", "method", "version", "operational",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ExperimentResult fields: {sorted(extra)}"
            )
        try:
            return cls(
                experiment_id=payload["experiment_id"],
                protocol_fingerprint=payload["protocol_fingerprint"],
                arm_records=dict(payload.get("arm_records", {})),
                benchmark_identity=dict(
                    payload.get("benchmark_identity", {})
                ),
                agent_identity=dict(payload.get("agent_identity", {})),
                environment_identity=dict(
                    payload.get("environment_identity", {})
                ),
                configuration=dict(payload.get("configuration", {})),
                lineage=dict(payload.get("lineage", {})),
                metrics_nd=dict(payload.get("metrics_nd", {})),
                metrics_nh=dict(payload.get("metrics_nh", {})),
                metrics_rd=dict(payload.get("metrics_rd", {})),
                metrics_rh=dict(payload.get("metrics_rh", {})),
                delta_diagnostic=dict(
                    payload.get("delta_diagnostic", {})
                ),
                delta_heldout=dict(payload.get("delta_heldout", {})),
                rq4_vector=dict(payload.get("rq4_vector", {})),
                rq4_status=payload.get(
                    "rq4_status", RQ4_DESCRIPTIVE_ONLY
                ),
                result_state=payload.get("result_state", "INCONCLUSIVE"),
                failure_detail=payload.get("failure_detail", ""),
                integrity_checks=dict(
                    payload.get("integrity_checks", {})
                ),
                method=payload.get("method", RESULT_METHOD),
                method_version=payload.get("version", RESULT_VERSION),
                operational=dict(payload.get("operational", {})),
            )
        except KeyError as exc:
            raise ValueError(
                f"ExperimentResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Scientific identity: operational block excluded by construction."""
        payload = self.to_dict()
        payload.pop("operational", None)
        return fingerprint_of_dict(payload)

    def save(self, path: str) -> None:
        """Persist the result as canonical JSON (artefact store)."""
        import os

        _require_str(path, "path")
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                self.to_dict(), handle, sort_keys=True,
                separators=(",", ":"),
            )

    @classmethod
    def load(cls, path: str) -> "ExperimentResult":
        """Reload a persisted result; unknown fields rejected."""
        _require_str(path, "path")
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise ProvenanceError(
                f"cannot load experiment result from {path!r}: {exc}"
            ) from exc
        return cls.from_dict(payload)
