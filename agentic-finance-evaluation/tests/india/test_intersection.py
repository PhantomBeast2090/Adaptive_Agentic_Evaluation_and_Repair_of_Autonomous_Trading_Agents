from datetime import date

import pandas as pd

from src.india.coverage_audit import CoverageAuditor


def _frame(start: str, end: str) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.date_range(start, end, freq="D")})


def test_common_intersection_is_calculated_from_audited_data():
    auditor = CoverageAuditor()
    auditor.audit_dataset("equities", _frame("2020-01-01", "2022-12-31"), [], "date")
    auditor.audit_dataset("vix", _frame("2021-01-01", "2023-12-31"), [], "date")
    result = auditor.compute_common_intersection(min_coverage_days=365)
    assert result.earliest_common == date(2021, 1, 1)
    assert result.latest_common == date(2022, 12, 31)
    assert result.included_datasets == ["equities", "vix"]


def test_short_dataset_is_excluded_with_reason():
    auditor = CoverageAuditor()
    auditor.audit_dataset("long", _frame("2020-01-01", "2022-12-31"), [], "date")
    auditor.audit_dataset("short", _frame("2022-01-01", "2022-02-01"), [], "date")
    result = auditor.compute_common_intersection(min_coverage_days=365)
    assert result.excluded_datasets == ["short"]
    assert "Coverage too short" in result.exclusion_reasons["short"]


def test_partial_mandatory_set_is_not_computable():
    auditor = CoverageAuditor()
    auditor.audit_dataset("nifty50", _frame("2020-01-01", "2022-12-31"), [], "date")
    result = auditor.compute_common_intersection(
        mandatory_datasets=["nifty50", "india_vix"],
        eligible_datasets={"nifty50"},
        min_coverage_days=365,
    )
    assert result.status == "INCOMPLETE_DATASET_SET"
    assert result.earliest_common is None
    assert result.missing_mandatory_datasets == ["india_vix"]
