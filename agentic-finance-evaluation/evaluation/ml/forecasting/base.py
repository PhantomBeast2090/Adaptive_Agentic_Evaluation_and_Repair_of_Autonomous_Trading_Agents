"""Normalised forecast output (model-independent).

Every foundation-model adapter converts its native output into
``ForecastOutput``. Downstream code (features, miner, persistence)
never sees Chronos/TimesFM internals. Unknown fields are rejected on
deserialisation, mirroring E0 conventions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Frozen forecast contract (authorised 2026-09-26; changes need protocol).
FORECAST_HORIZONS = (1, 3, 5)
FORECAST_QUANTILES = (0.1, 0.5, 0.9)
FORECAST_CONTEXT_LENGTH = 256


def context_fingerprint(series: Mapping[str, List[float]],
                        stamps: Mapping[str, List[str]]) -> str:
    """SHA over the exact PIT input; T+1 changes must not match."""
    payload = {"series": {k: list(v) for k, v in sorted(series.items())},
               "stamps": {k: list(v) for k, v in sorted(stamps.items())}}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ForecastOutput:
    """One normalised per-decision forecast with full provenance."""

    model_id: str
    model_version: str
    checkpoint_revision: str
    decision_id: str
    instrument: str
    decision_timestamp: str
    context_fingerprint: str
    horizons: Tuple[int, ...]
    quantiles: Tuple[float, ...]
    # quantile_paths[q][h]: forecast level at horizon h (None if absent)
    quantile_paths: Tuple[Tuple[Optional[float], ...], ...]
    reference_level: Optional[float]  # last PIT close (return basis)
    deterministic_seed: Optional[int]
    status: str  # ModelStatus value
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "checkpoint_revision": self.checkpoint_revision,
            "decision_id": self.decision_id,
            "instrument": self.instrument,
            "decision_timestamp": self.decision_timestamp,
            "context_fingerprint": self.context_fingerprint,
            "horizons": list(self.horizons),
            "quantiles": list(self.quantiles),
            "quantile_paths": [list(p) for p in self.quantile_paths],
            "reference_level": self.reference_level,
            "deterministic_seed": self.deterministic_seed,
            "status": self.status,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ForecastOutput":
        known = {"model_id", "model_version", "checkpoint_revision",
                 "decision_id", "instrument", "decision_timestamp",
                 "context_fingerprint", "horizons", "quantiles",
                 "quantile_paths", "reference_level",
                 "deterministic_seed", "status", "failure_reason"}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(f"unknown ForecastOutput fields: {unknown}")
        for field in known:
            if field not in payload:
                raise ValueError(f"missing ForecastOutput field: {field}")
        return cls(
            model_id=str(payload["model_id"]),
            model_version=str(payload["model_version"]),
            checkpoint_revision=str(payload["checkpoint_revision"]),
            decision_id=str(payload["decision_id"]),
            instrument=str(payload["instrument"]),
            decision_timestamp=str(payload["decision_timestamp"]),
            context_fingerprint=str(payload["context_fingerprint"]),
            horizons=tuple(payload["horizons"]),
            quantiles=tuple(payload["quantiles"]),
            quantile_paths=tuple(
                tuple(v for v in path)
                for path in payload["quantile_paths"]),
            reference_level=(None if payload["reference_level"] is None
                             else float(payload["reference_level"])),
            deterministic_seed=(None if payload["deterministic_seed"] is None
                                else int(payload["deterministic_seed"])),
            status=str(payload["status"]),
            failure_reason=(None if payload["failure_reason"] is None
                            else str(payload["failure_reason"])),
        )

    def output_fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(
            self.to_dict(), sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
