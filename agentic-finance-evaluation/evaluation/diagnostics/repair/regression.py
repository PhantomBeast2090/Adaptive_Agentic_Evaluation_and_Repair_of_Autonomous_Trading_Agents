"""Regression analysis over validation comparisons (E2-F).

``analyze_regression`` compares repaired-candidate measurements against
original-agent controls, window by window, reusing the E1 metric
vocabulary with zero new metrics:

* diagnostic window: candidate@diagnostic vs original@diagnostic
  (stored baseline — never rerun);
* held-out window: candidate@heldout vs original@heldout (same unseen
  window, so regime cannot confound the comparison).

Every comparison is an explicit ``RegressionFinding``: the two values,
their delta (``None`` whenever either side is undefined — undefined
stays undefined, never fabricated), and an optional tolerance verdict.
Tolerances are opt-in named rules (``ToleranceRule``); with none
supplied, findings carry ``within_tolerance=None`` and no pass/fail is
asserted. Uncalibrated thresholds are never invented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw


@dataclass(frozen=True)
class ToleranceRule:
    """Named absolute-epsilon tolerance for one metric (opt-in)."""

    metric_name: str
    epsilon: float = 0.0
    method: str = "absolute-epsilon"
    version: str = "v1"

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must be a non-empty string")
        if (
            not isinstance(self.epsilon, (int, float))
            or isinstance(self.epsilon, bool)
            or self.epsilon != self.epsilon
            or self.epsilon in (float("inf"), float("-inf"))
            or float(self.epsilon) < 0
        ):
            raise ValueError("epsilon must be a finite non-negative number")
        object.__setattr__(self, "epsilon", float(self.epsilon))
        for field_name in ("method", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def allows(self, delta: Optional[float]) -> Optional[bool]:
        """Whether a delta is within tolerance (None when unjudgeable)."""
        if delta is None:
            return None
        return abs(delta) <= self.epsilon

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "epsilon": self.epsilon,
            "method": self.method,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToleranceRule":
        if not isinstance(payload, Mapping):
            raise TypeError("ToleranceRule payload must be a mapping")
        known = {"metric_name", "epsilon", "method", "version"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ToleranceRule fields: {sorted(extra)}"
            )
        try:
            return cls(
                metric_name=payload["metric_name"],
                epsilon=payload.get("epsilon", 0.0),
                method=payload.get("method", "absolute-epsilon"),
                version=payload.get("version", "v1"),
            )
        except KeyError as exc:
            raise ValueError(
                f"ToleranceRule payload missing {exc}"
            ) from exc


@dataclass(frozen=True)
class RegressionFinding:
    """One explicit metric comparison between validation and control."""

    metric_name: str
    window_label: str
    reference_value: Optional[float] = None
    validation_value: Optional[float] = None
    delta: Optional[float] = None
    tolerance: Optional[Mapping[str, Any]] = None
    within_tolerance: Optional[bool] = None

    def __post_init__(self) -> None:
        for field_name in ("metric_name", "window_label"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for field_name in ("reference_value", "validation_value", "delta"):
            value = getattr(self, field_name)
            if value is not None:
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or value != value
                    or value in (float("inf"), float("-inf"))
                ):
                    raise ValueError(
                        f"{field_name} must be a finite number or None"
                    )
                object.__setattr__(self, field_name, float(value))
        expected = None
        if (
            self.reference_value is not None
            and self.validation_value is not None
        ):
            expected = self.validation_value - self.reference_value
        if self.delta is None:
            if expected is not None:
                raise ValueError(
                    "delta must equal validation minus reference when "
                    "both sides are defined"
                )
        elif expected is None:
            raise ValueError(
                "delta must be None when either side is undefined"
            )
        elif abs(self.delta - expected) > 1e-9:
            raise ValueError(
                "delta must equal validation minus reference"
            )
        if self.tolerance is not None:
            if not isinstance(self.tolerance, Mapping):
                raise TypeError("tolerance must be a mapping or None")
            object.__setattr__(
                self, "tolerance", freeze(dict(self.tolerance))
            )
        if self.within_tolerance is not None and not isinstance(
            self.within_tolerance, bool
        ):
            raise TypeError("within_tolerance must be a bool or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "window_label": self.window_label,
            "reference_value": self.reference_value,
            "validation_value": self.validation_value,
            "delta": self.delta,
            "tolerance": (
                thaw(self.tolerance) if self.tolerance is not None else None
            ),
            "within_tolerance": self.within_tolerance,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegressionFinding":
        if not isinstance(payload, Mapping):
            raise TypeError("RegressionFinding payload must be a mapping")
        known = {
            "metric_name", "window_label", "reference_value",
            "validation_value", "delta", "tolerance", "within_tolerance",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RegressionFinding fields: {sorted(extra)}"
            )
        try:
            tolerance = payload.get("tolerance")
            return cls(
                metric_name=payload["metric_name"],
                window_label=payload["window_label"],
                reference_value=payload.get("reference_value"),
                validation_value=payload.get("validation_value"),
                delta=payload.get("delta"),
                tolerance=dict(tolerance) if tolerance is not None else None,
                within_tolerance=payload.get("within_tolerance"),
            )
        except KeyError as exc:
            raise ValueError(
                f"RegressionFinding payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class RegressionAnalysis:
    """The complete finding set for one validation exercise."""

    analysis_id: str
    candidate_id: str
    validation_fingerprint: str
    findings: Tuple[RegressionFinding, ...] = field(default_factory=tuple)
    method: str = ""
    method_version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "analysis_id",
            "candidate_id",
            "validation_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        findings = self.findings
        if isinstance(findings, str) or not isinstance(findings, (tuple, list)):
            raise TypeError(
                "findings must be a tuple/list of RegressionFinding"
            )
        findings = tuple(findings)
        if not findings:
            raise ValueError("findings must be non-empty")
        for finding in findings:
            if not isinstance(finding, RegressionFinding):
                raise TypeError(
                    "findings must contain RegressionFinding, "
                    f"got {type(finding).__name__}"
                )
        keys = [
            (finding.metric_name, finding.window_label)
            for finding in findings
        ]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "findings must not contain duplicate (metric, window) pairs"
            )
        object.__setattr__(self, "findings", findings)
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def finding(self, metric_name: str, window_label: str) -> RegressionFinding:
        """Fetch one finding by metric and window."""
        for item in self.findings:
            if (
                item.metric_name == metric_name
                and item.window_label == window_label
            ):
                return item
        raise KeyError(f"no finding for {(metric_name, window_label)!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "candidate_id": self.candidate_id,
            "validation_fingerprint": self.validation_fingerprint,
            "findings": [item.to_dict() for item in self.findings],
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegressionAnalysis":
        if not isinstance(payload, Mapping):
            raise TypeError("RegressionAnalysis payload must be a mapping")
        known = {
            "analysis_id", "candidate_id", "validation_fingerprint",
            "findings", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RegressionAnalysis fields: {sorted(extra)}"
            )
        try:
            return cls(
                analysis_id=payload["analysis_id"],
                candidate_id=payload["candidate_id"],
                validation_fingerprint=payload["validation_fingerprint"],
                findings=tuple(
                    RegressionFinding.from_dict(item)
                    for item in payload.get("findings", ())
                ),
                method=payload["method"],
                method_version=payload.get("version", ""),
            )
        except KeyError as exc:
            raise ValueError(
                f"RegressionAnalysis payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


REGRESSION_METHOD = "metric-delta-comparison"
REGRESSION_VERSION = "v1"


def analyze_regression(
    *,
    analysis_id: str,
    candidate_id: str,
    validation_fingerprint: str,
    comparisons: Tuple[
        Tuple[str, str, Optional[float], Optional[float]], ...
    ],
    tolerances: Tuple[ToleranceRule, ...] = (),
) -> RegressionAnalysis:
    """Build explicit per-metric findings from windowed comparisons.

    Each comparison is ``(window_label, metric_name, reference_value,
    validation_value)`` with finite values or ``None``. No thresholds
    are invented: tolerance verdicts appear only for metrics with an
    explicitly supplied rule.
    """
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise ValueError("analysis_id must be a non-empty string")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must be a non-empty string")
    if isinstance(comparisons, str) or not isinstance(
        comparisons, (tuple, list)
    ):
        raise TypeError("comparisons must be a tuple/list of triples")
    comparisons = tuple(comparisons)
    if not comparisons:
        raise ValueError("comparisons must be non-empty")
    rules = {}
    for rule in tolerances:
        if not isinstance(rule, ToleranceRule):
            raise TypeError(
                "tolerances must contain ToleranceRule, "
                f"got {type(rule).__name__}"
            )
        rules[rule.metric_name] = rule
    findings = []
    for entry in comparisons:
        if (
            not isinstance(entry, (tuple, list)) or len(tuple(entry)) != 4
        ):
            raise TypeError(
                "each comparison must be a "
                "(window_label, metric_name, reference, validation) tuple"
            )
        window_label, name, reference, validation = tuple(entry)
        if not isinstance(window_label, str) or not window_label:
            raise ValueError("comparison window labels must be non-empty")
        if not isinstance(name, str) or not name:
            raise ValueError("comparison metric names must be non-empty")
        delta = None
        if reference is not None and validation is not None:
            delta = float(validation) - float(reference)
        rule = rules.get(name)
        findings.append(
            RegressionFinding(
                metric_name=name,
                window_label=window_label,
                reference_value=reference,
                validation_value=validation,
                delta=delta,
                tolerance=rule.to_dict() if rule is not None else None,
                within_tolerance=(
                    rule.allows(delta) if rule is not None else None
                ),
            )
        )
    return RegressionAnalysis(
        analysis_id=analysis_id,
        candidate_id=candidate_id,
        validation_fingerprint=validation_fingerprint,
        findings=tuple(findings),
        method=REGRESSION_METHOD,
        method_version=REGRESSION_VERSION,
    )
