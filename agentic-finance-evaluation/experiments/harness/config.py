"""E3-E frozen experiment configuration (orchestration data only).

``ExperimentConfig`` carries every scientific input the harness needs
and nothing it must decide. Production configurations are built from
the frozen E3-C manifest via ``from_manifest`` and verified with
``verify_against_manifest``; hand-built configurations exist for unit
tests only and any deviation fails closed. No defaults, no silent
normalisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import freeze, thaw
from experiments.harness.errors import ManifestMismatchError

ARMS = ("N-D", "N-H", "D-F", "D-A", "R-D", "R-H")

DIAGNOSTIC_POLICIES = ("fixed", "adaptive")

REQUIRED_BUDGET_KEYS = (
    "max_tests",
    "max_repairs",
    "max_validation_runs",
)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_window(value: object, field_name: str) -> Tuple[str, str]:
    if (
        isinstance(value, str)
        or not isinstance(value, (tuple, list))
        or len(tuple(value)) != 2
    ):
        raise ValueError(f"{field_name} must be a (start, end) date pair")
    start, end = str(value[0]), str(value[1])
    if not start.strip() or not end.strip():
        raise ValueError(f"{field_name} bounds must be non-empty strings")
    if end < start:
        raise ValueError(f"{field_name} end must not precede start")
    return (start, end)


@dataclass(frozen=True)
class ExperimentConfig:
    """Immutable, fully explicit experimental configuration."""

    protocol_version: str
    e3d_fingerprint: str
    benchmark_id: str
    benchmark_version: str
    benchmark_module: str
    agent_id: str
    agent_version: str
    environment_fingerprint: str
    dataset_fingerprints: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    calendar_fingerprint: str = ""
    diagnostic_window: Tuple[str, str] = ("", "")
    heldout_window: Tuple[str, str] = ("", "")
    universe: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    transaction_cost_bps: float = 0.0
    initial_cash: float = 0.0
    strict_pit: bool = True
    vintage_policy: str = ""
    diagnostic_policy: str = ""
    candidate_pool: Tuple[str, ...] = ()
    fixed_sequence: Tuple[str, ...] = ()
    budgets: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    seed_provenance: Optional[int] = None
    arm: str = ""
    result_dir: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "protocol_version",
            "e3d_fingerprint",
            "benchmark_id",
            "benchmark_version",
            "benchmark_module",
            "agent_id",
            "agent_version",
            "environment_fingerprint",
            "calendar_fingerprint",
            "vintage_policy",
            "diagnostic_policy",
            "arm",
            "result_dir",
        ):
            _require_str(getattr(self, field_name), field_name)
        if self.arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}, got {self.arm!r}")
        if self.diagnostic_policy not in DIAGNOSTIC_POLICIES:
            raise ValueError(
                f"diagnostic_policy must be one of {DIAGNOSTIC_POLICIES}, "
                f"got {self.diagnostic_policy!r}"
            )
        object.__setattr__(
            self, "diagnostic_window",
            _require_window(self.diagnostic_window, "diagnostic_window"),
        )
        object.__setattr__(
            self, "heldout_window",
            _require_window(self.heldout_window, "heldout_window"),
        )
        if self.heldout_window[0] <= self.diagnostic_window[1]:
            raise ValueError(
                "heldout_window must start strictly after "
                "diagnostic_window ends"
            )
        if not isinstance(self.universe, Mapping) or not dict(self.universe):
            raise ValueError("universe must be a non-empty mapping")
        object.__setattr__(self, "universe", freeze(dict(self.universe)))
        object.__setattr__(
            self, "dataset_fingerprints",
            freeze(dict(self.dataset_fingerprints)),
        )
        for field_name in ("transaction_cost_bps", "initial_cash"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value != value
                or value in (float("inf"), float("-inf"))
                or float(value) < 0
            ):
                raise ValueError(
                    f"{field_name} must be a finite non-negative number"
                )
            object.__setattr__(self, field_name, float(value))
        if not isinstance(self.strict_pit, bool):
            raise TypeError("strict_pit must be a bool")
        if not isinstance(self.candidate_pool, (tuple, list)):
            raise TypeError("candidate_pool must be a tuple/list")
        pool = tuple(self.candidate_pool)
        if not pool or any(
            not isinstance(t, str) or not t for t in pool
        ):
            raise ValueError(
                "candidate_pool must be a non-empty tuple of test ids"
            )
        if len(set(pool)) != len(pool):
            raise ValueError("candidate_pool must not contain duplicates")
        object.__setattr__(self, "candidate_pool", pool)
        if not isinstance(self.fixed_sequence, (tuple, list)):
            raise TypeError("fixed_sequence must be a tuple/list")
        sequence = tuple(self.fixed_sequence)
        if not sequence or any(
            not isinstance(t, str) or not t for t in sequence
        ):
            raise ValueError(
                "fixed_sequence must be a non-empty tuple of test ids"
            )
        if any(t not in pool for t in sequence):
            raise ValueError(
                "fixed_sequence test ids must all belong to candidate_pool"
            )
        object.__setattr__(self, "fixed_sequence", sequence)
        if not isinstance(self.budgets, Mapping):
            raise TypeError("budgets must be a mapping")
        budgets = dict(self.budgets)
        for key in REQUIRED_BUDGET_KEYS:
            value = budgets.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"budgets[{key!r}] must be a non-negative int"
                )
        object.__setattr__(self, "budgets", freeze(budgets))
        if self.seed_provenance is not None and (
            isinstance(self.seed_provenance, bool)
            or not isinstance(self.seed_provenance, int)
        ):
            raise TypeError("seed_provenance must be an int or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "e3d_fingerprint": self.e3d_fingerprint,
            "benchmark_id": self.benchmark_id,
            "benchmark_version": self.benchmark_version,
            "benchmark_module": self.benchmark_module,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "environment_fingerprint": self.environment_fingerprint,
            "dataset_fingerprints": thaw(self.dataset_fingerprints),
            "calendar_fingerprint": self.calendar_fingerprint,
            "diagnostic_window": list(self.diagnostic_window),
            "heldout_window": list(self.heldout_window),
            "universe": thaw(self.universe),
            "transaction_cost_bps": self.transaction_cost_bps,
            "initial_cash": self.initial_cash,
            "strict_pit": self.strict_pit,
            "vintage_policy": self.vintage_policy,
            "diagnostic_policy": self.diagnostic_policy,
            "candidate_pool": list(self.candidate_pool),
            "fixed_sequence": list(self.fixed_sequence),
            "budgets": thaw(self.budgets),
            "seed_provenance": self.seed_provenance,
            "arm": self.arm,
            "result_dir": self.result_dir,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentConfig":
        if not isinstance(payload, Mapping):
            raise TypeError("ExperimentConfig payload must be a mapping")
        known = {
            "protocol_version", "e3d_fingerprint", "benchmark_id",
            "benchmark_version", "benchmark_module", "agent_id",
            "agent_version", "environment_fingerprint",
            "dataset_fingerprints", "calendar_fingerprint",
            "diagnostic_window", "heldout_window", "universe",
            "transaction_cost_bps", "initial_cash", "strict_pit",
            "vintage_policy", "diagnostic_policy", "candidate_pool",
            "fixed_sequence", "budgets", "seed_provenance", "arm",
            "result_dir",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ExperimentConfig fields: {sorted(extra)}"
            )
        try:
            return cls(
                protocol_version=payload["protocol_version"],
                e3d_fingerprint=payload["e3d_fingerprint"],
                benchmark_id=payload["benchmark_id"],
                benchmark_version=payload["benchmark_version"],
                benchmark_module=payload["benchmark_module"],
                agent_id=payload["agent_id"],
                agent_version=payload["agent_version"],
                environment_fingerprint=payload["environment_fingerprint"],
                dataset_fingerprints=dict(
                    payload.get("dataset_fingerprints", {})
                ),
                calendar_fingerprint=payload["calendar_fingerprint"],
                diagnostic_window=tuple(payload["diagnostic_window"]),
                heldout_window=tuple(payload["heldout_window"]),
                universe=dict(payload["universe"]),
                transaction_cost_bps=payload["transaction_cost_bps"],
                initial_cash=payload["initial_cash"],
                strict_pit=payload["strict_pit"],
                vintage_policy=payload["vintage_policy"],
                diagnostic_policy=payload["diagnostic_policy"],
                candidate_pool=tuple(payload["candidate_pool"]),
                fixed_sequence=tuple(payload["fixed_sequence"]),
                budgets=dict(payload["budgets"]),
                seed_provenance=payload.get("seed_provenance"),
                arm=payload["arm"],
                result_dir=payload["result_dir"],
            )
        except KeyError as exc:
            raise ValueError(
                f"ExperimentConfig payload missing {exc}"
            ) from exc

    def verify_against_manifest(self, manifest: Mapping[str, Any]) -> None:
        """Fail closed unless every scientific field matches the manifest."""
        if not isinstance(manifest, Mapping):
            raise TypeError("manifest must be a mapping")

        def _mismatch(field_name: str, expected: object, actual: object) -> None:
            if expected != actual:
                raise ManifestMismatchError(
                    f"{field_name} {actual!r} does not match frozen "
                    f"manifest {expected!r}: failing closed, no normalisation"
                )

        temporal = manifest.get("temporal", {})
        _mismatch(
            "diagnostic_window",
            (
                str(temporal.get("diagnostic_start")),
                str(temporal.get("diagnostic_end")),
            ),
            self.diagnostic_window,
        )
        _mismatch(
            "heldout_window",
            (
                str(temporal.get("heldout_start")),
                str(temporal.get("heldout_end")),
            ),
            self.heldout_window,
        )
        environment = manifest.get("environment", {})
        _mismatch(
            "universe",
            {
                asset: list(instruments)
                for asset, instruments in dict(
                    environment.get("universe", {})
                ).items()
            },
            {
                asset: list(instruments)
                for asset, instruments in dict(self.universe).items()
            },
        )
        _mismatch(
            "transaction_cost_bps",
            float(environment.get("transaction_cost_bps", -1.0)),
            self.transaction_cost_bps,
        )
        _mismatch(
            "initial_cash",
            float(environment.get("initial_cash", -1.0)),
            self.initial_cash,
        )
        pool = manifest.get("candidate_pool", [])
        _mismatch(
            "candidate_pool",
            sorted(
                entry["test_id"] for entry in pool
                if isinstance(entry, Mapping) and "test_id" in entry
            ),
            sorted(self.candidate_pool),
        )
        _mismatch(
            "fixed_sequence",
            list(manifest.get("fixed_sequence", {}).get("order", [])),
            list(self.fixed_sequence),
        )
        manifest_budgets = manifest.get("budgets", {})
        for key in REQUIRED_BUDGET_KEYS:
            _mismatch(
                f"budgets[{key}]",
                manifest_budgets.get(key),
                dict(self.budgets).get(key),
            )
        rows = manifest.get("benchmarks", [])
        match = [
            row for row in rows
            if isinstance(row, Mapping)
            and row.get("agent_id") == self.benchmark_id
            and str(row.get("version")) == self.benchmark_version
        ]
        if not match:
            raise ManifestMismatchError(
                f"benchmark {self.benchmark_id}@"
                f"{self.benchmark_version} is not a frozen manifest entry"
            )
