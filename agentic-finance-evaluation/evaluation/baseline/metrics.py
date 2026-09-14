"""Deterministic baseline metrics (E1).

Every function here is pure in the recorded ``DecisionRecord`` trajectory
plus the run's initial cash. Each returns a ``MetricResult`` whose value is
either a measured number or ``None`` with a non-empty ``undefined_reason``.
A ``0.0`` always means "measured zero"; ``None`` always means "not
measurable from this evidence" — the same convention as
``evaluation/metrics/static_metrics.py``.

Deliberate limitations (documented, not hidden):

* Volatility/Sharpe/Sortino are **per-session** statistics. Nothing is
  annualised inside the evaluator (D3); annualised presentation can be
  derived later without changing the canonical artefact.
* Concentration is **cost-basis** (``quantity × avg_cost`` from recorded
  position snapshots) because mark-to-market prices per instrument are not
  part of the decision record. It measures cost concentration, not market
  exposure concentration.
* Net exposure and leverage are reported as identities of gross exposure:
  the Indian environment is long-only with no leverage, so
  ``net ≡ gross`` and ``leverage ≡ gross`` by construction.
* No parametric tail metrics (VaR/CVaR) are estimated: session-grain
  samples cannot support tail estimation. ``worst_session_return`` is the
  honest downside statistic at this grain.
* No metric is a failure label. Thresholds and failure semantics belong to
  later milestones, never here.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.fingerprints import fingerprint_of_dict

from environment.indian.actions import STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE
from environment.portfolio.accounting import (
    STATUS_EXECUTED_FULL,
    STATUS_EXECUTED_PARTIAL,
)

EXECUTED_STATUSES = (STATUS_EXECUTED_FULL, STATUS_EXECUTED_PARTIAL)


@dataclass(frozen=True)
class MetricResult:
    """One named baseline measurement, possibly explicitly undefined."""

    name: str
    value: Optional[float] = None
    unit: str = "ratio"
    undefined_reason: Optional[str] = None
    derivation: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("metric name must be a non-empty string")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError("metric unit must be a non-empty string")
        if not isinstance(self.derivation, str) or not self.derivation.strip():
            raise ValueError("metric derivation must be a non-empty string")
        if self.value is None:
            if (
                not isinstance(self.undefined_reason, str)
                or not self.undefined_reason.strip()
            ):
                raise ValueError(
                    f"metric {self.name!r}: value=None requires a "
                    "non-empty undefined_reason"
                )
        else:
            if (
                not isinstance(self.value, (int, float))
                or isinstance(self.value, bool)
                or self.value != self.value
                or self.value in (float("inf"), float("-inf"))
            ):
                raise ValueError(
                    f"metric {self.name!r}: value must be finite or None"
                )
            object.__setattr__(self, "value", float(self.value))
            if self.undefined_reason is not None:
                raise ValueError(
                    f"metric {self.name!r}: undefined_reason must be None "
                    "when value is present"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "undefined_reason": self.undefined_reason,
            "derivation": self.derivation,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MetricResult":
        if not isinstance(payload, Mapping):
            raise TypeError("MetricResult payload must be a mapping")
        known = {"name", "value", "unit", "undefined_reason", "derivation"}
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown MetricResult fields: {sorted(extra)}")
        try:
            return cls(
                name=payload["name"],
                value=payload.get("value"),
                unit=payload.get("unit", "ratio"),
                undefined_reason=payload.get("undefined_reason"),
                derivation=payload.get("derivation", ""),
            )
        except KeyError as exc:
            raise ValueError(f"MetricResult payload missing {exc}") from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def _derivation(name: str) -> str:
    return f"e1.{name}.v1"


def _measured(name: str, value: float, unit: str) -> MetricResult:
    return MetricResult(
        name=name, value=value, unit=unit, derivation=_derivation(name)
    )


def _undefined(name: str, unit: str, reason: str) -> MetricResult:
    return MetricResult(
        name=name,
        value=None,
        unit=unit,
        undefined_reason=reason,
        derivation=_derivation(name),
    )


def _checked_records(records: object) -> Tuple[DecisionRecord, ...]:
    if isinstance(records, (str, bytes)) or not isinstance(
        records, (tuple, list)
    ):
        raise TypeError("records must be a tuple/list of DecisionRecord")
    items = tuple(records)
    for item in items:
        if not isinstance(item, DecisionRecord):
            raise TypeError(
                "metrics derive only from DecisionRecord, "
                f"got {type(item).__name__}"
            )
    return items


def _equity_curve(
    records: Tuple[DecisionRecord, ...], initial_cash: float
) -> List[float]:
    if not records:
        return []
    curve = [float(records[0].portfolio_before["total_equity"])]
    for record in records:
        curve.append(float(record.portfolio_after["total_equity"]))
    return curve


def _step_returns(
    records: Tuple[DecisionRecord, ...], initial_cash: float
) -> Optional[List[float]]:
    curve = _equity_curve(records, initial_cash)
    if len(curve) < 2:
        return None
    if any(base <= 0 for base in curve[:-1]):
        return None
    return [
        (curve[i + 1] / curve[i]) - 1.0 for i in range(len(curve) - 1)
    ]


def _all_executions(
    records: Tuple[DecisionRecord, ...],
) -> List[Mapping[str, Any]]:
    out: List[Mapping[str, Any]] = []
    for record in records:
        out.extend(record.executions)
    return out


# -- performance -------------------------------------------------------


def cumulative_return(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    if not items:
        return _undefined(
            "cumulative_return", "ratio", "no decision records"
        )
    base = float(items[0].portfolio_before["total_equity"])
    final = float(items[-1].portfolio_after["total_equity"])
    if base <= 0:
        return _undefined(
            "cumulative_return", "ratio",
            "return undefined against a non-positive base",
        )
    return _measured("cumulative_return", (final / base) - 1.0, "ratio")


def volatility_per_session(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    returns = _step_returns(items, initial_cash)
    if returns is None:
        return _undefined(
            "volatility_per_session", "ratio",
            "fewer than two sessions or non-positive equity base",
        )
    if len(returns) < 2:
        return _undefined(
            "volatility_per_session", "ratio",
            "dispersion undefined for a single session",
        )
    return _measured(
        "volatility_per_session", statistics.pstdev(returns), "ratio"
    )


def sharpe_per_session(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    returns = _step_returns(items, initial_cash)
    if returns is None or len(returns) < 2:
        return _undefined(
            "sharpe_per_session", "ratio",
            "fewer than two sessions or non-positive equity base",
        )
    dispersion = statistics.pstdev(returns)
    if dispersion == 0:
        return _undefined(
            "sharpe_per_session", "ratio",
            "zero return dispersion; ratio undefined",
        )
    return _measured(
        "sharpe_per_session",
        statistics.fmean(returns) / dispersion,
        "ratio",
    )


def sortino_per_session(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    returns = _step_returns(items, initial_cash)
    if returns is None or len(returns) < 2:
        return _undefined(
            "sortino_per_session", "ratio",
            "fewer than two sessions or non-positive equity base",
        )
    downside = statistics.fmean([min(0.0, r) ** 2 for r in returns]) ** 0.5
    if downside == 0:
        return _undefined(
            "sortino_per_session", "ratio",
            "no negative sessions; downside deviation is zero",
        )
    return _measured(
        "sortino_per_session",
        statistics.fmean(returns) / downside,
        "ratio",
    )


def max_drawdown(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    curve = _equity_curve(items, initial_cash)
    if not curve:
        return _undefined("max_drawdown", "ratio", "no decision records")
    peak = curve[0]
    worst = 0.0
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return _measured("max_drawdown", worst, "ratio")


def worst_session_return(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    returns = _step_returns(items, initial_cash)
    if not returns:
        return _undefined(
            "worst_session_return", "ratio",
            "no measurable sessions or non-positive equity base",
        )
    return _measured("worst_session_return", min(returns), "ratio")


# -- trading -----------------------------------------------------------


def order_count(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    return _measured(
        "order_count",
        float(sum(len(record.submitted_orders) for record in items)),
        "count",
    )


def executed_notional(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    total = 0.0
    for execution in _all_executions(items):
        total += float(execution["executed_quantity"]) * float(
            execution["execution_price"]
        )
    return _measured("executed_notional", total, "inr")


def turnover(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    curve = _equity_curve(items, initial_cash)
    if not curve:
        return _undefined("turnover", "ratio", "no decision records")
    mean_equity = statistics.fmean(curve)
    if mean_equity <= 0:
        return _undefined(
            "turnover", "ratio", "non-positive mean equity; ratio undefined"
        )
    notional = 0.0
    for execution in _all_executions(items):
        notional += float(execution["executed_quantity"]) * float(
            execution["execution_price"]
        )
    return _measured("turnover", notional / mean_equity, "ratio")


def transaction_cost_total(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    return _measured(
        "transaction_cost_total",
        float(sum(record.transaction_cost for record in items)),
        "inr",
    )


def concentration_cost_basis_max(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    best: Optional[float] = None
    for record in items:
        positions = record.portfolio_after.get("positions", {})
        costs = [
            float(pos.get("quantity", 0.0)) * float(pos.get("avg_cost", 0.0))
            for pos in positions.values()
            if isinstance(pos, Mapping)
        ]
        costs = [cost for cost in costs if cost > 0]
        if not costs:
            continue
        weight = max(costs) / sum(costs)
        best = weight if best is None else max(best, weight)
    if best is None:
        return _undefined(
            "concentration_cost_basis_max", "ratio",
            "no position ever held; cost-basis concentration undefined",
        )
    return _measured("concentration_cost_basis_max", best, "ratio")


def position_persistence(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    if not items:
        return _undefined(
            "position_persistence", "ratio", "no decision records"
        )
    held = 0
    for record in items:
        positions = record.portfolio_after.get("positions", {})
        if any(
            isinstance(pos, Mapping) and float(pos.get("quantity", 0.0)) > 0
            for pos in positions.values()
        ):
            held += 1
    return _measured("position_persistence", held / len(items), "ratio")


def reversal_rate(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    last_side: Dict[str, str] = {}
    pairs = 0
    reversals = 0
    for record in items:
        for execution in record.executions:
            if float(execution["executed_quantity"]) <= 0:
                continue
            side = str(execution["action_normalized"])
            if side not in ("BUY", "SELL"):
                continue
            key = str(execution["instrument"])
            previous = last_side.get(key)
            if previous is not None:
                pairs += 1
                if previous != side:
                    reversals += 1
            last_side[key] = side
    if pairs == 0:
        return _undefined(
            "reversal_rate", "ratio",
            "no consecutive executed same-instrument pairs",
        )
    return _measured("reversal_rate", reversals / pairs, "ratio")


def inactivity_rate(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    if not items:
        return _undefined("inactivity_rate", "ratio", "no decision records")
    idle = sum(1 for record in items if len(record.submitted_orders) == 0)
    return _measured("inactivity_rate", idle / len(items), "ratio")


# -- risk (exposure identities of a long-only, unlevered environment) ---


def _exposure_series(
    records: Tuple[DecisionRecord, ...],
) -> List[float]:
    series = []
    for record in records:
        exposure = record.portfolio_after.get("exposure")
        if (
            isinstance(exposure, (int, float))
            and not isinstance(exposure, bool)
            and exposure == exposure
        ):
            series.append(float(exposure))
    return series


def gross_exposure_max(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    series = _exposure_series(items)
    if not series:
        return _undefined(
            "gross_exposure_max", "ratio",
            "no exposure snapshots recorded",
        )
    return _measured("gross_exposure_max", max(series), "ratio")


def gross_exposure_mean(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    series = _exposure_series(items)
    if not series:
        return _undefined(
            "gross_exposure_mean", "ratio",
            "no exposure snapshots recorded",
        )
    return _measured(
        "gross_exposure_mean", statistics.fmean(series), "ratio"
    )


def net_exposure_max(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    series = _exposure_series(items)
    if not series:
        return _undefined(
            "net_exposure_max", "ratio",
            "no exposure snapshots recorded",
        )
    return MetricResult(
        name="net_exposure_max",
        value=max(series),
        unit="ratio",
        derivation="e1.net_exposure_max.v1:long-only-no-short-selling;net-identical-to-gross-by-construction",
    )


def leverage_max(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    series = _exposure_series(items)
    if not series:
        return _undefined(
            "leverage_max", "ratio",
            "no exposure snapshots recorded",
        )
    return MetricResult(
        name="leverage_max",
        value=max(series),
        unit="ratio",
        derivation="e1.leverage_max.v1:environment-prohibits-leverage;leverage-identical-to-gross-exposure-by-construction",
    )


# -- validity ----------------------------------------------------------


def _status_counts(
    records: Tuple[DecisionRecord, ...],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for execution in _all_executions(records):
        status = str(execution["execution_status"])
        counts[status] = counts.get(status, 0) + 1
    return counts


def invalid_order_count(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    counts = _status_counts(items)
    invalid = sum(
        count
        for status, count in counts.items()
        if status not in EXECUTED_STATUSES
    )
    return _measured("invalid_order_count", float(invalid), "count")


def invalid_order_rate(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    submitted = sum(len(record.submitted_orders) for record in items)
    if submitted == 0:
        return _undefined(
            "invalid_order_rate", "ratio", "no submitted orders"
        )
    counts = _status_counts(items)
    invalid = sum(
        count
        for status, count in counts.items()
        if status not in EXECUTED_STATUSES
    )
    return _measured("invalid_order_rate", invalid / submitted, "ratio")


def universe_violation_count(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    counts = _status_counts(items)
    return _measured(
        "universe_violation_count",
        float(counts.get(STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE, 0)),
        "count",
    )


def no_price_count(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    counts = _status_counts(items)
    return _measured(
        "no_price_count",
        float(counts.get("NOOP_NO_PRICE", 0)),
        "count",
    )


def calendar_gate_count(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    counts = _status_counts(items)
    gated = counts.get("NOOP_MARKET_CLOSED", 0) + counts.get(
        "NOOP_UNKNOWN_CALENDAR", 0
    )
    return _measured("calendar_gate_count", float(gated), "count")


def unavailable_info_session_count(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    sessions = sum(
        1 for record in items if len(record.unavailable_assets) > 0
    )
    return _measured(
        "unavailable_info_session_count", float(sessions), "count"
    )


def unavailable_info_rate(
    records: Sequence[DecisionRecord], initial_cash: float
) -> MetricResult:
    items = _checked_records(records)
    if not items:
        return _undefined(
            "unavailable_info_rate", "ratio", "no decision records"
        )
    sessions = sum(
        1 for record in items if len(record.unavailable_assets) > 0
    )
    return _measured(
        "unavailable_info_rate", sessions / len(items), "ratio"
    )


METRIC_FUNCTIONS = (
    cumulative_return,
    volatility_per_session,
    sharpe_per_session,
    sortino_per_session,
    max_drawdown,
    worst_session_return,
    order_count,
    executed_notional,
    turnover,
    transaction_cost_total,
    concentration_cost_basis_max,
    position_persistence,
    reversal_rate,
    inactivity_rate,
    gross_exposure_max,
    gross_exposure_mean,
    net_exposure_max,
    leverage_max,
    invalid_order_count,
    invalid_order_rate,
    universe_violation_count,
    no_price_count,
    calendar_gate_count,
    unavailable_info_session_count,
    unavailable_info_rate,
)


def compute_all(
    records: Sequence[DecisionRecord], initial_cash: float
) -> Tuple[MetricResult, ...]:
    """Compute every baseline metric in a fixed, deterministic order."""
    items = _checked_records(records)
    if (
        not isinstance(initial_cash, (int, float))
        or isinstance(initial_cash, bool)
        or initial_cash != initial_cash
        or initial_cash in (float("inf"), float("-inf"))
    ):
        raise ValueError("initial_cash must be a finite number")
    if float(initial_cash) < 0:
        raise ValueError("initial_cash must be non-negative")
    return tuple(
        function(items, float(initial_cash)) for function in METRIC_FUNCTIONS
    )
