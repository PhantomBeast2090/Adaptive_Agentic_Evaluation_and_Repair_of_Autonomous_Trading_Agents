"""Baseline evaluation configuration (E1).

A ``BaselineConfig`` is the complete, explicit policy for one deterministic
baseline run: agent-independent evaluation identity, environment window and
universe, cost/cash/PIT settings, budget, and a provenance-only seed.

There are no hidden defaults. Every field except ``seed`` is required at
construction. ``seed`` defaults to ``None`` and is recorded for provenance
only: every E1 component is deterministic and no code path consumes it
(mirroring ``Trajectory.seed`` in ``evaluation/episode_runner.py``).

``to_env_config()`` renders the exact mapping consumed by
``IndianMultiAssetEnvironment``; the runner constructs the environment
from it so the evaluated environment always matches the recorded config.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw

VINTAGE_POLICIES = ("explicit", "earliest_available", "latest_available")

UNIVERSE_ASSETS = ("nse_equity", "mcx_gold")


def _require_timestamp(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a YYYY-MM-DD string")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be YYYY-MM-DD, got {value!r}"
        ) from exc
    return value


def _require_non_negative_number(value: object, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value != value
        or value in (float("inf"), float("-inf"))
    ):
        raise ValueError(f"{field_name} must be a finite number")
    if float(value) < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return float(value)


@dataclass(frozen=True)
class BaselineConfig:
    """Explicit, immutable policy for one baseline evaluation."""

    evaluation_id: str
    start_date: str
    end_date: str
    universe: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    transaction_cost_bps: float = 5.0
    initial_cash: float = 100000.0
    strict_pit: bool = True
    vintage_policy: str = "explicit"
    budget: EvaluationBudget = None  # type: ignore[assignment]
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation_id, str) or not self.evaluation_id.strip():
            raise ValueError("evaluation_id must be a non-empty string")
        start = _require_timestamp(self.start_date, "start_date")
        end = _require_timestamp(self.end_date, "end_date")
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)
        if start > end:
            raise ValueError(
                f"start_date {start} must not be after end_date {end}"
            )
        object.__setattr__(
            self, "universe", freeze(self._checked_universe(self.universe))
        )
        object.__setattr__(
            self, "transaction_cost_bps",
            _require_non_negative_number(
                self.transaction_cost_bps, "transaction_cost_bps"
            ),
        )
        object.__setattr__(
            self, "initial_cash",
            _require_non_negative_number(self.initial_cash, "initial_cash"),
        )
        if not isinstance(self.strict_pit, bool):
            raise TypeError(
                "strict_pit must be a bool, "
                f"got {type(self.strict_pit).__name__}"
            )
        if self.vintage_policy not in VINTAGE_POLICIES:
            raise ValueError(
                f"unknown vintage_policy {self.vintage_policy!r}; "
                f"known: {list(VINTAGE_POLICIES)}"
            )
        if not isinstance(self.budget, EvaluationBudget):
            raise TypeError("budget must be an EvaluationBudget")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise TypeError("seed must be an int or None (provenance only)")

    @staticmethod
    def _checked_universe(value: object) -> Dict[str, Tuple[str, ...]]:
        if not isinstance(value, Mapping):
            raise TypeError("universe must be a mapping")
        unknown = set(value) - set(UNIVERSE_ASSETS)
        if unknown:
            raise ValueError(f"unknown universe assets: {sorted(unknown)}")
        checked: Dict[str, Tuple[str, ...]] = {}
        total = 0
        for asset_id in UNIVERSE_ASSETS:
            instruments = value.get(asset_id, ())
            if isinstance(instruments, str) or not isinstance(
                instruments, (tuple, list)
            ):
                raise TypeError(
                    f"universe[{asset_id!r}] must be a tuple/list of strings"
                )
            items = tuple(instruments)
            for item in items:
                if not isinstance(item, str) or not item:
                    raise ValueError(
                        f"universe[{asset_id!r}] entries must be non-empty strings"
                    )
            if len(set(items)) != len(items):
                raise ValueError(
                    f"universe[{asset_id!r}] must not contain duplicates"
                )
            checked[asset_id] = items
            total += len(items)
        if total == 0:
            raise ValueError(
                "universe must name at least one tradable instrument"
            )
        return checked

    def to_env_config(self) -> Dict[str, Any]:
        """Render the exact config mapping for ``IndianMultiAssetEnvironment``."""
        return {
            "strict_pit": self.strict_pit,
            "vintage_policy": self.vintage_policy,
            "transaction_cost_bps": self.transaction_cost_bps,
            "initial_cash": self.initial_cash,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "universe": {
                asset_id: list(instruments)
                for asset_id, instruments in self.universe.items()
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "universe": {
                asset_id: list(instruments)
                for asset_id, instruments in thaw(self.universe).items()
            },
            "transaction_cost_bps": self.transaction_cost_bps,
            "initial_cash": self.initial_cash,
            "strict_pit": self.strict_pit,
            "vintage_policy": self.vintage_policy,
            "budget": self.budget.to_dict(),
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BaselineConfig":
        if not isinstance(payload, Mapping):
            raise TypeError("BaselineConfig payload must be a mapping")
        known = {
            "evaluation_id", "start_date", "end_date", "universe",
            "transaction_cost_bps", "initial_cash", "strict_pit",
            "vintage_policy", "budget", "seed",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown BaselineConfig fields: {sorted(extra)}")
        try:
            return cls(
                evaluation_id=payload["evaluation_id"],
                start_date=payload["start_date"],
                end_date=payload["end_date"],
                universe=dict(payload.get("universe", {})),
                transaction_cost_bps=payload.get("transaction_cost_bps", 5.0),
                initial_cash=payload.get("initial_cash", 100000.0),
                strict_pit=payload.get("strict_pit", True),
                vintage_policy=payload.get("vintage_policy", "explicit"),
                budget=EvaluationBudget.from_dict(payload["budget"]),
                seed=payload.get("seed"),
            )
        except KeyError as exc:
            raise ValueError(
                f"BaselineConfig payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every config field."""
        return fingerprint_of_dict(self.to_dict())
