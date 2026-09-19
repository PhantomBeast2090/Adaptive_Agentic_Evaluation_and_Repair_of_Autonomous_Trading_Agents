"""Independent validation of repaired candidates (E2-F).

``run_validation`` executes a repaired candidate through the existing
E1 ``run_baseline`` machinery — the same runner, the same metrics, the
same environment authority — on two windows:

* the diagnostic window (did the diagnosed failure move?);
* a later, non-overlapping held-out window of caller-chosen dates
  (does anything about the repair survive unseen market conditions?).

The original agent is additionally run on the held-out window so the
generalisation comparison is same-window, not regime-confounded. The
stored original baseline artefact supplies the diagnostic-window
control without rerunning anything already recorded.

The validator reads artefacts, computes comparisons, and writes a
frozen ``ValidationReport``. It never judges the repair — acceptance
lives in ``regression.py`` — and it never modifies the candidate,
the original, or any baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.baseline.results import BaselineResult
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw


@dataclass(frozen=True)
class ValidationRun:
    """One validation episode: window label, result identity, metric map."""

    label: str
    window: Tuple[str, str]
    result_fingerprint: str
    metrics: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        for field_name in ("label", "result_fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        window = self.window
        if (
            isinstance(window, str)
            or not isinstance(window, (tuple, list))
            or len(tuple(window)) != 2
        ):
            raise TypeError("window must be a (start, end) date pair")
        for day in tuple(window):
            if not isinstance(day, str) or not day.strip():
                raise ValueError("window bounds must be date strings")
        object.__setattr__(self, "window", (window[0], window[1]))
        if not isinstance(self.metrics, Mapping):
            raise TypeError("metrics must be a mapping")
        cleaned: Dict[str, Optional[float]] = {}
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name:
                raise ValueError("metric names must be non-empty strings")
            if value is None:
                cleaned[name] = None
            elif (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value != value
                or value in (float("inf"), float("-inf"))
            ):
                raise ValueError(
                    f"metric {name!r} must be a finite number or None"
                )
            else:
                cleaned[name] = float(value)
        object.__setattr__(self, "metrics", freeze(cleaned))

    def value_of(self, name: str) -> Optional[float]:
        """Fetch one metric value (None when absent or undefined)."""
        value = dict(self.metrics).get(name)
        return None if value is None else float(value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "window": list(self.window),
            "result_fingerprint": self.result_fingerprint,
            "metrics": thaw(self.metrics),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationRun":
        if not isinstance(payload, Mapping):
            raise TypeError("ValidationRun payload must be a mapping")
        known = {"label", "window", "result_fingerprint", "metrics"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ValidationRun fields: {sorted(extra)}"
            )
        try:
            return cls(
                label=payload["label"],
                window=tuple(payload["window"]),
                result_fingerprint=payload["result_fingerprint"],
                metrics=dict(payload.get("metrics", {})),
            )
        except KeyError as exc:
            raise ValueError(
                f"ValidationRun payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class ValidationReport:
    """Frozen record of one independent validation exercise."""

    validation_id: str
    candidate_id: str
    candidate_fingerprint: str
    baseline_evaluation_id: str
    baseline_fingerprint: str
    runs: Tuple[ValidationRun, ...] = field(default_factory=tuple)
    method: str = ""
    method_version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "validation_id",
            "candidate_id",
            "candidate_fingerprint",
            "baseline_evaluation_id",
            "baseline_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        runs = self.runs
        if isinstance(runs, str) or not isinstance(runs, (tuple, list)):
            raise TypeError("runs must be a tuple/list of ValidationRun")
        runs = tuple(runs)
        if not runs:
            raise ValueError("runs must be non-empty")
        for run in runs:
            if not isinstance(run, ValidationRun):
                raise TypeError(
                    "runs must contain ValidationRun, "
                    f"got {type(run).__name__}"
                )
        labels = [run.label for run in runs]
        if len(set(labels)) != len(labels):
            raise ValueError("run labels must not contain duplicates")
        object.__setattr__(self, "runs", runs)
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def run(self, label: str) -> ValidationRun:
        """Fetch one validation run by label."""
        for item in self.runs:
            if item.label == label:
                return item
        raise KeyError(f"no validation run {label!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "candidate_id": self.candidate_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "baseline_evaluation_id": self.baseline_evaluation_id,
            "baseline_fingerprint": self.baseline_fingerprint,
            "runs": [run.to_dict() for run in self.runs],
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationReport":
        if not isinstance(payload, Mapping):
            raise TypeError("ValidationReport payload must be a mapping")
        known = {
            "validation_id", "candidate_id", "candidate_fingerprint",
            "baseline_evaluation_id", "baseline_fingerprint", "runs",
            "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ValidationReport fields: {sorted(extra)}"
            )
        try:
            return cls(
                validation_id=payload["validation_id"],
                candidate_id=payload["candidate_id"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                baseline_evaluation_id=payload["baseline_evaluation_id"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                runs=tuple(
                    ValidationRun.from_dict(item)
                    for item in payload.get("runs", ())
                ),
                method=payload["method"],
                method_version=payload.get("version", ""),
            )
        except KeyError as exc:
            raise ValueError(
                f"ValidationReport payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


VALIDATOR_METHOD = "e1-rerun-comparison"
VALIDATOR_VERSION = "v1"


def _metric_map(result: BaselineResult) -> Dict[str, Optional[float]]:
    return {
        metric.name: metric.value for metric in result.metrics
    }


def _validation_config_for(
    baseline: BaselineResult,
    window: Tuple[str, str],
    seed: Optional[int],
) -> BaselineConfig:
    return BaselineConfig(
        evaluation_id=f"{baseline.evaluation_id}-validation",
        start_date=window[0],
        end_date=window[1],
        universe={
            asset: tuple(instruments)
            for asset, instruments in dict(
                baseline.config.universe
            ).items()
        },
        transaction_cost_bps=baseline.config.transaction_cost_bps,
        initial_cash=baseline.config.initial_cash,
        strict_pit=baseline.config.strict_pit,
        vintage_policy=baseline.config.vintage_policy,
        budget=baseline.config.budget,
        seed=seed,
    )


def _as_iso(day: object) -> date:
    if isinstance(day, date):
        return day
    text = str(day)
    year, month, dom = (int(part) for part in text.split("-"))
    return date(year, month, dom)


def run_validation(
    *,
    validation_id: str,
    candidate_id: str,
    candidate_fingerprint: str,
    candidate_agent: Any,
    original_agent: Any,
    baseline: BaselineResult,
    heldout_window: Tuple[str, str],
    seed: Optional[int] = None,
    base_dir: str = ".",
) -> Tuple[ValidationReport, Tuple[BaselineResult, ...]]:
    """Validate a repaired candidate with three E1 comparison runs.

    Runs the candidate on the diagnostic window and on a later,
    non-overlapping held-out window, plus the original agent on the
    held-out window so generalisation is compared same-window. The
    stored original baseline supplies the diagnostic-window control
    without rerunning anything already recorded.

    Returns ``(report, artefacts)`` where artefacts are the three fresh
    ``BaselineResult`` objects in run order. Raises ``ValueError`` for
    scope violations (overlapping or non-later held-out window) before
    any execution, and propagates environment failures explicitly.
    """
    if not isinstance(validation_id, str) or not validation_id.strip():
        raise ValueError("validation_id must be a non-empty string")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must be a non-empty string")
    if not isinstance(baseline, BaselineResult):
        raise TypeError(
            "baseline must be a BaselineResult, "
            f"got {type(baseline).__name__}"
        )
    if (
        not isinstance(heldout_window, (tuple, list))
        or len(tuple(heldout_window)) != 2
    ):
        raise TypeError("heldout_window must be a (start, end) date pair")
    diag_end = _as_iso(baseline.config.end_date)
    held_start = _as_iso(heldout_window[0])
    held_end = _as_iso(heldout_window[1])
    if held_end < held_start:
        raise ValueError("held-out window end must not precede its start")
    if held_start <= diag_end:
        raise ValueError(
            "held-out window must start strictly after the diagnostic "
            f"window ends ({diag_end}); temporal separation is what makes "
            "generalisation evidence independent"
        )
    diag_window = (
        str(baseline.config.start_date),
        str(baseline.config.end_date),
    )
    runs: list = []
    artefacts: list = []
    plan = (
        ("candidate_diagnostic", candidate_agent, diag_window),
        ("candidate_heldout", candidate_agent,
         (str(held_start), str(held_end))),
        ("original_heldout", original_agent,
         (str(held_start), str(held_end))),
    )
    for label, agent, window in plan:
        result = run_baseline(
            agent,
            _validation_config_for(baseline, window, seed),
            base_dir=base_dir,
        )
        artefacts.append(result)
        runs.append(
            ValidationRun(
                label=label,
                window=window,
                result_fingerprint=result.fingerprint(),
                metrics=_metric_map(result),
            )
        )
    report = ValidationReport(
        validation_id=validation_id,
        candidate_id=candidate_id,
        candidate_fingerprint=candidate_fingerprint,
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        runs=tuple(runs),
        method=VALIDATOR_METHOD,
        method_version=VALIDATOR_VERSION,
    )
    return report, tuple(artefacts)
