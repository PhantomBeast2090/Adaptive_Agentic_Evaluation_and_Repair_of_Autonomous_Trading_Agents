from datetime import date

import pandas as pd

from src.india.coverage_audit import (
    CoverageAuditor,
    audit_missingness,
    audit_temporal_consistency,
)


def test_coverage_reports_dates_duplicates_and_missingness():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-04"]),
            "symbol": ["A", "A", "A"],
            "close": [1.0, 1.0, None],
        }
    )
    auditor = CoverageAuditor()
    result = auditor.audit_dataset(
        "equity",
        frame,
        required_fields=["close", "volume"],
        date_col="date",
        identifier_cols=["symbol"],
        expected_frequency="daily",
        is_trading_day_data=True,
    )
    assert result.temporal.earliest == date(2024, 1, 2)
    assert result.temporal.latest == date(2024, 1, 4)
    assert result.temporal.duplicate_timestamps == 1
    assert result.temporal.duplicate_identifier_pairs == 1
    assert result.missingness[0].missing_count == 1
    assert result.missingness[1].missing_count == 3


def test_temporal_consistency_detects_unsorted_dates_and_gaps():
    frame = pd.DataFrame({"date": pd.to_datetime(["2024-01-10", "2024-01-01"])})
    result = audit_temporal_consistency(
        frame, date_col="date", expected_frequency="monthly", max_gap_days=5
    )
    assert result.is_monotonic is False
    assert result.gaps_detected == [(date(2024, 1, 1), date(2024, 1, 10))]


def test_missingness_percentage_is_quantified():
    result = audit_missingness(pd.DataFrame({"x": [1, None, None]}), ["x"])
    assert result[0].missing_pct == 100 * 2 / 3
