"""Coverage Audit Library for Indian Market Data.

Provides reusable audit functions and CoverageAuditor class used by:
  - scripts/audit_indian_data_coverage.py  (CLI audit runner)
  - tests/india/test_coverage_audit.py     (unit tests)

Key outputs:
  - Per-dataset: temporal coverage, duplicates, missingness, frequency checks
  - Cross-dataset: common usable intersection (computed from actual data)
  - Calendar consistency check against Indian trading calendar

IMPORTANT: This module does NOT choose experiment splits.
It reports what is there. Split design is a separate methodological step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from src.india.calendar import NSETradingCalendar

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TemporalCoverage:
    earliest: Optional[date]
    latest: Optional[date]
    total_observations: int
    unique_dates: int
    duplicate_timestamps: int
    duplicate_identifier_pairs: int   # e.g. (date, symbol) duplicates


@dataclass
class MissingnessResult:
    field_name: str
    missing_count: int
    total_count: int

    @property
    def missing_pct(self) -> float:
        if self.total_count == 0:
            return 0.0
        return 100.0 * self.missing_count / self.total_count


@dataclass
class TemporalConsistencyResult:
    is_monotonic: bool
    gaps_detected: List[Tuple[date, date]]   # (gap_start, gap_end) exclusive
    expected_frequency: Optional[str]
    frequency_violations: int                 # rows that violate expected frequency


@dataclass
class CalendarConsistencyResult:
    """Consistency with Indian trading / business calendar."""
    non_trading_day_observations: int         # Obs on days that should be holidays/weekends
    missing_trading_days: int                 # Expected trading days with no observation
    checked_against: str                      # e.g. "NSE_TRADING_CALENDAR", "WEEKDAY_ONLY"
    missing_dates: List[date] = field(default_factory=list)
    calendar_available: bool = True


@dataclass
class AvailabilityConsistencyResult:
    """For macro/policy data: check observation_date vs availability_date."""
    total_records: int
    violations: int                           # availability_date < observation_date
    violation_examples: List[Dict[str, Any]]  # Up to 5 examples


@dataclass
class DatasetAuditResult:
    dataset_id: str
    temporal: TemporalCoverage
    missingness: List[MissingnessResult]
    consistency: TemporalConsistencyResult
    calendar: Optional[CalendarConsistencyResult]
    availability: Optional[AvailabilityConsistencyResult]
    notes: List[str] = field(default_factory=list)


@dataclass
class IntersectionResult:
    """Common usable date range across all mandatory datasets."""
    included_datasets: List[str]
    excluded_datasets: List[str]
    exclusion_reasons: Dict[str, str]
    earliest_common: Optional[date]
    latest_common: Optional[date]
    total_common_days: int
    jointly_usable_dates: List[date] = field(default_factory=list)
    limiting_datasets: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    status: str = "COMPUTABLE_COMMON_INTERSECTION"
    missing_mandatory_datasets: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Calendar compatibility helpers
# ---------------------------------------------------------------------------

# NSE is closed on these national holidays (approximate recurring set).
# For a production system, use pandas_market_calendars or an official NSE
# holiday list. Here we use a lightweight rule-based approach.
def is_likely_indian_trading_day(d: date) -> bool:
    """Compatibility weekday-only predicate; not research-grade calendar data."""
    return d.weekday() < 5


def expected_trading_days(start: date, end: date) -> Set[date]:
    """Return weekday candidates for backwards compatibility only."""
    days: Set[date] = set()
    current = start
    while current <= end:
        if is_likely_indian_trading_day(current):
            days.add(current)
        current += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# Core audit functions
# ---------------------------------------------------------------------------

def audit_temporal_coverage(
    df: pd.DataFrame,
    date_col: Optional[str] = None,
    identifier_cols: Optional[List[str]] = None,
) -> TemporalCoverage:
    """Compute temporal coverage statistics for a DataFrame.

    Args:
        df: The dataset to audit.
        date_col: Name of the date column. If None, uses the index.
        identifier_cols: Additional columns that form a compound key with date
                         (e.g. ['symbol'] for equity data).
    """
    if date_col is not None:
        dates = pd.to_datetime(df[date_col])
    else:
        dates = pd.to_datetime(df.index)

    if len(dates) == 0:
        return TemporalCoverage(
            earliest=None, latest=None,
            total_observations=0, unique_dates=0,
            duplicate_timestamps=0, duplicate_identifier_pairs=0,
        )

    earliest = dates.min().date()
    latest = dates.max().date()
    total_obs = len(dates)
    unique_dates = dates.nunique()
    dup_timestamps = int((dates.duplicated()).sum())

    dup_pairs = 0
    if identifier_cols:
        key_cols = ([date_col] if date_col else []) + identifier_cols
        existing = [c for c in key_cols if c in df.columns]
        if existing:
            dup_pairs = int(df.duplicated(subset=existing).sum())

    return TemporalCoverage(
        earliest=earliest,
        latest=latest,
        total_observations=total_obs,
        unique_dates=unique_dates,
        duplicate_timestamps=dup_timestamps,
        duplicate_identifier_pairs=dup_pairs,
    )


def audit_missingness(
    df: pd.DataFrame,
    required_fields: List[str],
) -> List[MissingnessResult]:
    """Compute per-field missingness for required fields."""
    results = []
    for field_name in required_fields:
        if field_name not in df.columns:
            results.append(MissingnessResult(
                field_name=field_name,
                missing_count=len(df),
                total_count=len(df),
            ))
        else:
            missing = int(df[field_name].isna().sum())
            results.append(MissingnessResult(
                field_name=field_name,
                missing_count=missing,
                total_count=len(df),
            ))
    return results


def audit_temporal_consistency(
    df: pd.DataFrame,
    date_col: Optional[str] = None,
    expected_frequency: Optional[str] = None,
    max_gap_days: int = 10,
) -> TemporalConsistencyResult:
    """Check monotonicity and detect unexpected temporal gaps.

    Args:
        df: Dataset to audit.
        date_col: Date column or None to use index.
        expected_frequency: 'daily', 'weekly', 'monthly', or None.
        max_gap_days: Gaps larger than this (in calendar days) are flagged.
                      Set appropriately per frequency (e.g. 10 for daily,
                      60 for monthly).
    """
    if date_col is not None:
        dates = pd.to_datetime(df[date_col])
    else:
        dates = pd.to_datetime(df.index)

    if len(dates) == 0:
        return TemporalConsistencyResult(
            is_monotonic=True, gaps_detected=[], expected_frequency=expected_frequency,
            frequency_violations=0,
        )

    is_monotonic = bool(dates.is_monotonic_increasing)
    sorted_dates = dates.sort_values()

    # Gap detection
    gaps: List[Tuple[date, date]] = []
    dates_list = sorted_dates.tolist()
    for i in range(1, len(dates_list)):
        delta = (dates_list[i] - dates_list[i - 1]).days
        if delta > max_gap_days:
            gaps.append((dates_list[i - 1].date(), dates_list[i].date()))

    # Frequency violations
    freq_violations = 0
    if expected_frequency == "daily":
        # Expect consecutive calendar days (weekdays only roughly)
        pass  # Handled by calendar audit
    elif expected_frequency == "monthly":
        # Expect approximately one obs per calendar month
        months = sorted_dates.dt.to_period("M")
        month_counts = months.value_counts()
        freq_violations = int((month_counts > 1).sum())

    return TemporalConsistencyResult(
        is_monotonic=is_monotonic,
        gaps_detected=gaps,
        expected_frequency=expected_frequency,
        frequency_violations=freq_violations,
    )


def audit_calendar_consistency(
    df: pd.DataFrame,
    date_col: Optional[str] = None,
    calendar_type: str = "NSE_TRADING",
    calendar: Optional[NSETradingCalendar] = None,
) -> CalendarConsistencyResult:
    """Check alignment with Indian trading calendar.

    For trading-day datasets (equities, indices, VIX, currency):
      - Observations on weekends/holidays are suspicious
      - Missing expected trading days are flagged
    """
    if date_col is not None:
        dates = set(pd.to_datetime(df[date_col]).dt.date)
    else:
        dates = set(pd.to_datetime(df.index).date)

    if not dates:
        return CalendarConsistencyResult(0, 0, calendar_type)

    start = min(dates)
    end = max(dates)
    if calendar is None:
        return CalendarConsistencyResult(
            non_trading_day_observations=sum(d.weekday() >= 5 for d in dates),
            missing_trading_days=0,
            checked_against="UNAVAILABLE",
            missing_dates=[],
            calendar_available=False,
        )
    try:
        expected = calendar.trading_days(start, end)
    except ValueError:
        return CalendarConsistencyResult(
            non_trading_day_observations=sum(d.weekday() >= 5 for d in dates),
            missing_trading_days=0,
            checked_against=f"UNAVAILABLE:{calendar.coverage.version}",
            missing_dates=[],
            calendar_available=False,
        )
    non_trading = sum(not calendar.is_trading_day(d) for d in dates)
    missing_dates = sorted(expected - dates)

    return CalendarConsistencyResult(
        non_trading_day_observations=non_trading,
        missing_trading_days=len(missing_dates),
        checked_against=f"{calendar_type}:{calendar.coverage.version}",
        missing_dates=missing_dates,
        calendar_available=True,
    )


def audit_availability_consistency(
    df: pd.DataFrame,
    observation_col: str = "observation_date",
    availability_col: str = "availability_date",
    allow_pre_observation: bool = False,
) -> AvailabilityConsistencyResult:
    """Verify release timing for retrospective macro records.

    Policy events may legitimately be announced before their effective
    observation date; callers can opt into that semantics explicitly.
    """
    total = len(df)
    if observation_col not in df.columns or availability_col not in df.columns:
        return AvailabilityConsistencyResult(
            total_records=total,
            violations=0,
            violation_examples=[],
        )

    obs = pd.to_datetime(df[observation_col])
    avail = pd.to_datetime(df[availability_col])
    bad_mask = avail < obs if not allow_pre_observation else pd.Series(False, index=df.index)

    violations = int(bad_mask.sum())
    examples = []
    if violations > 0:
        bad_rows = df[bad_mask].head(5)
        for _, row in bad_rows.iterrows():
            examples.append({
                "observation_date": str(row.get(observation_col)),
                "availability_date": str(row.get(availability_col)),
            })

    return AvailabilityConsistencyResult(
        total_records=total,
        violations=violations,
        violation_examples=examples,
    )


# ---------------------------------------------------------------------------
# CoverageAuditor — orchestrates all checks
# ---------------------------------------------------------------------------

class CoverageAuditor:
    """Orchestrate coverage audit across multiple datasets.

    Usage:
        auditor = CoverageAuditor()
        result = auditor.audit_dataset(
            dataset_id="nse_nifty50_daily",
            df=df,
            required_fields=["close", "volume"],
            date_col=None,          # uses index
            expected_frequency="daily",
            is_trading_day_data=True,
        )
        intersection = auditor.compute_common_intersection()
    """

    def __init__(self):
        self._dataset_coverages: Dict[str, Tuple[Optional[date], Optional[date]]] = {}
        self._usable_dates: Dict[str, Set[date]] = {}
        self._audit_results: Dict[str, DatasetAuditResult] = {}

    def audit_dataset(
        self,
        dataset_id: str,
        df: pd.DataFrame,
        required_fields: List[str],
        date_col: Optional[str] = None,
        identifier_cols: Optional[List[str]] = None,
        expected_frequency: Optional[str] = None,
        max_gap_days: int = 10,
        is_trading_day_data: bool = False,
        has_availability_date: bool = False,
        allow_pre_observation: bool = False,
        observation_col: str = "observation_date",
        availability_col: str = "availability_date",
        calendar: Optional[NSETradingCalendar] = None,
        session_dates: Optional[Set[date]] = None,
    ) -> DatasetAuditResult:
        """Run the full audit suite for one dataset."""
        temporal = audit_temporal_coverage(df, date_col, identifier_cols)
        missingness = audit_missingness(df, required_fields)
        consistency = audit_temporal_consistency(
            df, date_col, expected_frequency, max_gap_days
        )

        calendar_result = None
        if is_trading_day_data and temporal.earliest and temporal.latest:
            calendar_result = audit_calendar_consistency(df, date_col, calendar=calendar)

        availability_result = None
        if has_availability_date:
            availability_result = audit_availability_consistency(
                df, observation_col, availability_col, allow_pre_observation
            )

        notes = []
        if temporal.duplicate_timestamps > 0:
            notes.append(
                f"WARNING: {temporal.duplicate_timestamps} duplicate timestamps detected."
            )
            if identifier_cols:
                notes.append(
                    "Repeated dates are evaluated with identifier columns; "
                    "date repetition alone is not treated as a duplicate record."
                )
        if temporal.duplicate_identifier_pairs > 0:
            notes.append(
                f"WARNING: {temporal.duplicate_identifier_pairs} duplicate (date+id) pairs."
            )
        if not consistency.is_monotonic:
            notes.append("WARNING: Timestamps are not monotonically increasing.")
        if len(consistency.gaps_detected) > 0:
            notes.append(
                f"INFO: {len(consistency.gaps_detected)} gap(s) detected. "
                f"First: {consistency.gaps_detected[0]}"
            )

        result = DatasetAuditResult(
            dataset_id=dataset_id,
            temporal=temporal,
            missingness=missingness,
            consistency=consistency,
            calendar=calendar_result,
            availability=availability_result,
            notes=notes,
        )

        self._audit_results[dataset_id] = result
        self._dataset_coverages[dataset_id] = (temporal.earliest, temporal.latest)
        observed_dates = set(
            pd.to_datetime(df[date_col] if date_col else df.index)
            .dropna()
            .dt.date
        )
        valid_rows = df.copy()
        if required_fields:
            present_fields = [field for field in required_fields if field in valid_rows]
            if present_fields:
                valid_rows = valid_rows.dropna(subset=present_fields)
            else:
                valid_rows = valid_rows.iloc[0:0]
        valid_observed_dates = set(
            pd.Series(
                pd.to_datetime(
                    valid_rows[date_col] if date_col else valid_rows.index
                )
            ).dropna().dt.date
        )
        usable_dates = valid_observed_dates
        if is_trading_day_data and (
            calendar is None or calendar_result is None or not calendar_result.calendar_available
        ):
            usable_dates = set()
        if is_trading_day_data and calendar_result and calendar_result.calendar_available:
            usable_dates = {
                value for value in usable_dates if calendar.is_trading_day(value)
            }
        if has_availability_date:
            if availability_col not in df.columns:
                usable_dates = set()
            elif session_dates is not None:
                available = pd.to_datetime(
                    valid_rows[availability_col], errors="coerce"
                ).dropna()
                if is_trading_day_data:
                    candidate_sessions = {
                        session for session in session_dates
                        if calendar is not None and calendar.is_trading_day(session)
                    }
                    observed_by_session = valid_observed_dates
                    usable_dates = {
                        session
                        for session in candidate_sessions
                        if session in observed_by_session
                        and (available.dt.date <= session).any()
                    }
                else:
                    usable_dates = {
                        session
                        for session in session_dates
                        if (available.dt.date <= session).any()
                    }
            else:
                usable_dates = {
                    value for value in valid_observed_dates
                    if (pd.to_datetime(valid_rows[availability_col], errors="coerce").dt.date <= value).any()
                }
        self._usable_dates[dataset_id] = usable_dates
        return result

    def compute_common_intersection(
        self,
        mandatory_datasets: Optional[List[str]] = None,
        min_coverage_days: int = 365,
        eligible_datasets: Optional[Set[str]] = None,
    ) -> IntersectionResult:
        """Compute the longest clean common date range.

        The common intersection is the date range over which ALL mandatory
        datasets have coverage. Datasets with insufficient coverage are
        excluded and the reason is reported.

        This does NOT choose experiment splits — it reports available evidence.

        Args:
            mandatory_datasets: Which dataset IDs to require. If None, uses all.
            min_coverage_days: Datasets with fewer days are excluded with a note.
        """
        if mandatory_datasets is None:
            mandatory_datasets = list(self._dataset_coverages.keys())
        mandatory_datasets = list(dict.fromkeys(mandatory_datasets))
        missing = [
            dataset_id for dataset_id in mandatory_datasets
            if dataset_id not in self._dataset_coverages
        ]
        ineligible = [
            dataset_id for dataset_id in mandatory_datasets
            if eligible_datasets is not None and dataset_id not in eligible_datasets
        ]
        missing_or_ineligible = sorted(set(missing + ineligible))
        if missing_or_ineligible:
            reasons = {
                dataset_id: (
                    "Dataset not audited — no coverage data available."
                    if dataset_id in missing
                    else "Dataset is not experiment-eligible."
                )
                for dataset_id in missing_or_ineligible
            }
            return IntersectionResult(
                included_datasets=[],
                excluded_datasets=missing_or_ineligible,
                exclusion_reasons=reasons,
                earliest_common=None,
                latest_common=None,
                total_common_days=0,
                notes=[
                    "INCOMPLETE_DATASET_SET: the full mandatory dataset set is "
                    "not present and eligible; common intersection is not computable."
                ],
                status="INCOMPLETE_DATASET_SET",
                missing_mandatory_datasets=missing_or_ineligible,
            )

        included: List[str] = []
        excluded: List[str] = []
        exclusion_reasons: Dict[str, str] = {}

        for ds_id in mandatory_datasets:
            if ds_id not in self._dataset_coverages:
                excluded.append(ds_id)
                exclusion_reasons[ds_id] = "Dataset not audited — no coverage data available."
                continue

            earliest, latest = self._dataset_coverages[ds_id]
            if earliest is None or latest is None:
                excluded.append(ds_id)
                exclusion_reasons[ds_id] = "Dataset has no valid dates — possibly empty or not acquired."
                continue

            usable = self._usable_dates.get(ds_id, set())
            days = (latest - earliest).days
            if len(usable) < min_coverage_days:
                excluded.append(ds_id)
                exclusion_reasons[ds_id] = (
                    f"Coverage too short: {len(usable)} usable sessions < min "
                    f"{min_coverage_days} "
                    f"({earliest} to {latest})."
                )
                continue

            included.append(ds_id)

        notes: List[str] = []

        if excluded:
            notes.append(
                "INCOMPLETE_DATASET_SET: one or more mandatory datasets lack "
                "sufficient usable coverage; common intersection is not computable."
            )
            return IntersectionResult(
                included_datasets=included,
                excluded_datasets=excluded,
                exclusion_reasons=exclusion_reasons,
                earliest_common=None,
                latest_common=None,
                total_common_days=0,
                notes=notes,
                status="INCOMPLETE_DATASET_SET",
                missing_mandatory_datasets=excluded,
            )

        if not included:
            notes.append("No datasets with sufficient coverage — cannot compute intersection.")
            return IntersectionResult(
                included_datasets=included,
                excluded_datasets=excluded,
                exclusion_reasons=exclusion_reasons,
                earliest_common=None,
                latest_common=None,
                total_common_days=0,
                notes=notes,
                status="COMPUTABLE_COMMON_INTERSECTION",
            )

        usable_sets = [self._usable_dates[ds_id] for ds_id in included]
        common_dates = set.intersection(*usable_sets) if usable_sets else set()
        common_start = min(common_dates) if common_dates else None
        common_end = max(common_dates) if common_dates else None

        if not common_dates:
            notes.append(
                "WARNING: No common overlap exists among included datasets. "
                "The included datasets do not share any date range."
            )
            return IntersectionResult(
                included_datasets=included,
                excluded_datasets=excluded,
                exclusion_reasons=exclusion_reasons,
                earliest_common=None,
                latest_common=None,
                total_common_days=0,
                jointly_usable_dates=[],
                limiting_datasets=included,
                notes=notes,
                status="COMPUTABLE_COMMON_INTERSECTION",
            )

        total_days = len(common_dates)
        limiting = [
            dataset_id
            for dataset_id in included
            if len(self._usable_dates[dataset_id]) == min(
                len(self._usable_dates[item]) for item in included
            )
        ]
        notes.append(
            f"Common intersection: {common_start} → {common_end} "
            f"({total_days} jointly usable sessions, {len(included)} datasets)."
        )
        notes.append(
            "NOTE: Final experiment splits must be chosen based on further "
            "data quality and information-availability assessment — not merely "
            "from this intersection boundary."
        )

        return IntersectionResult(
            included_datasets=included,
            excluded_datasets=excluded,
            exclusion_reasons=exclusion_reasons,
            earliest_common=common_start,
            latest_common=common_end,
            total_common_days=total_days,
            jointly_usable_dates=sorted(common_dates),
            limiting_datasets=limiting,
            notes=notes,
            status="COMPUTABLE_COMMON_INTERSECTION",
        )

    def get_individual_coverages(self) -> Dict[str, Tuple[Optional[date], Optional[date]]]:
        """Return {dataset_id: (earliest, latest)} for all audited datasets."""
        return dict(self._dataset_coverages)

    def get_all_results(self) -> Dict[str, DatasetAuditResult]:
        return dict(self._audit_results)
