"""Orchestration configuration for closed-loop diagnosis (E2-E).

``OrchestrationConfig`` is the complete, explicit policy for one
diagnostic loop run. It carries bounds, identities, and provenance —
never artefacts:

* the baseline travels by ``(baseline_evaluation_id,
  baseline_fingerprint)`` reference only; the frozen artefact itself is
  a ``run()`` argument, never duplicated into configuration;
* ``window``/``universe`` episode scope is optional and defaults to the
  baseline's own scope when absent;
* ``seed`` is the loop base seed; iteration ``i`` executes with
  ``seed + i``, keeping every execution identity distinct yet
  reproducible;
* ``max_iterations`` bounds orchestration loop passes, distinctly from
  the test-execution budget (which only E2-B consumes);
* method/version fields are validated non-empty provenance; a
  cross-check test asserts they equal the frozen milestones' constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.baseline.config import UNIVERSE_ASSETS
from evaluation.contracts.fingerprints import (
    fingerprint_of_dict,
    freeze,
    thaw,
)


@dataclass(frozen=True)
class OrchestrationConfig:
    """Explicit, immutable policy for one orchestration run."""

    diagnostic_id: str
    baseline_evaluation_id: str
    baseline_fingerprint: str
    max_iterations: int = 5
    seed: int = 0
    agent_id: str = ""
    agent_version: str = ""
    window: Optional[Tuple[str, str]] = None
    universe: Optional[Mapping[str, Any]] = None
    base_dir: str = "."
    selector_method: str = "adaptive-discrimination"
    selector_version: str = "v1"
    interpreter_method: str = "directional-band"
    interpreter_version: str = "v1"

    def __post_init__(self) -> None:
        for field_name in (
            "diagnostic_id",
            "baseline_evaluation_id",
            "baseline_fingerprint",
            "agent_id",
            "agent_version",
            "base_dir",
            "selector_method",
            "selector_version",
            "interpreter_method",
            "interpreter_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or self.max_iterations < 1
        ):
            raise ValueError("max_iterations must be an int >= 1")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError(f"seed must be an int, got {self.seed!r}")
        if self.window is not None:
            if (
                not isinstance(self.window, (tuple, list))
                or len(self.window) != 2
            ):
                raise TypeError(
                    "window must be a (start_date, end_date) pair or None"
                )
            start, end = self.window
            for label, day in (("start_date", start), ("end_date", end)):
                if not isinstance(day, str) or not day.strip():
                    raise ValueError(f"window {label} must be a date string")
            if start > end:
                raise ValueError(
                    f"window start {start} must not be after end {end}"
                )
            object.__setattr__(self, "window", (start, end))
        if self.universe is not None:
            object.__setattr__(
                self, "universe", freeze(self._checked_universe(self.universe))
            )

    @staticmethod
    def _checked_universe(value: object) -> Dict[str, Tuple[str, ...]]:
        if not isinstance(value, Mapping):
            raise TypeError("universe must be a mapping or None")
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
                        f"universe[{asset_id!r}] entries must be non-empty "
                        "strings"
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "baseline_evaluation_id": self.baseline_evaluation_id,
            "baseline_fingerprint": self.baseline_fingerprint,
            "max_iterations": self.max_iterations,
            "seed": self.seed,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "window": list(self.window) if self.window is not None else None,
            "universe": (
                thaw(self.universe) if self.universe is not None else None
            ),
            "base_dir": self.base_dir,
            "selector_method": self.selector_method,
            "selector_version": self.selector_version,
            "interpreter_method": self.interpreter_method,
            "interpreter_version": self.interpreter_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OrchestrationConfig":
        if not isinstance(payload, Mapping):
            raise TypeError("OrchestrationConfig payload must be a mapping")
        known = {
            "diagnostic_id", "baseline_evaluation_id",
            "baseline_fingerprint", "max_iterations", "seed", "agent_id",
            "agent_version", "window", "universe", "base_dir",
            "selector_method", "selector_version", "interpreter_method",
            "interpreter_version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown OrchestrationConfig fields: {sorted(extra)}"
            )
        try:
            window = payload.get("window")
            return cls(
                diagnostic_id=payload["diagnostic_id"],
                baseline_evaluation_id=payload["baseline_evaluation_id"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                max_iterations=payload.get("max_iterations", 5),
                seed=payload.get("seed", 0),
                agent_id=payload["agent_id"],
                agent_version=payload["agent_version"],
                window=tuple(window) if window is not None else None,  # type: ignore[arg-type]
                universe=payload.get("universe"),
                base_dir=payload.get("base_dir", "."),
                selector_method=payload.get(
                    "selector_method", "adaptive-discrimination"
                ),
                selector_version=payload.get("selector_version", "v1"),
                interpreter_method=payload.get(
                    "interpreter_method", "directional-band"
                ),
                interpreter_version=payload.get("interpreter_version", "v1"),
            )
        except KeyError as exc:
            raise ValueError(
                f"OrchestrationConfig payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every configuration field."""
        return fingerprint_of_dict(self.to_dict())
