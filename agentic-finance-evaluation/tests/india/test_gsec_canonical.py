"""RBI 10Y G-Sec yield (FBIL) weekly acquisition/validation tests.

Covers the RBI '50 Macroeconomic Indicators' workbook Weekly sheet series
'10-Year G-Sec Yield (FBIL) (%)'. The raw workbook is immutable evidence
and is never modified by these tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.gsec_canonicalize import (
    TARGET_SERIES,
    TENOR,
    build_canonical,
    detect_overlaps,
    discover_gsec_raw_files,
    header_matches_gsec_schema,
    parse_period,
    read_weekly_series,
    validate_gsec_file,
)
from src.india.leakage_audit import LeakageAuditor
from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    EligibilityStatus,
    ValidationStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "fixed_income"
CANONICAL_PATH = PROJECT_ROOT / "data" / "processed" / "india" / "market" / "rbi_gsec_10y_weekly.csv"
MANIFEST_ID = "rbi_gsec_10y_yield"
RAW_NAME = "50 Macroeconomic Indicators.xlsx"


# 1. raw discovery
def test_raw_workbook_discovered():
    files = discover_gsec_raw_files(RAW_DIR)
    assert [path.name for path in files] == [RAW_NAME]
    assert files[0].stat().st_size == 103038


# 2. sheet/series targeting (Weekly sheet, exact series column)
def test_sheet_series_targeting():
    header, data_rows = read_weekly_series(RAW_DIR / RAW_NAME)
    assert header_matches_gsec_schema(header) is True
    assert header[1] == "Period"
    assert header[12] == TARGET_SERIES
    assert len(data_rows) == 465


# 3. schema validation
def test_schema_validation():
    audit, frame, excluded = validate_gsec_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.header_valid is True
    assert audit.sheet == "Weekly"
    assert audit.series == TARGET_SERIES
    assert audit.row_count == 465
    assert audit.parsed_date_count == 465
    assert audit.valid_row_count == 465
    assert excluded == []


# 4. date parsing (datetime Periods, all Fridays)
def test_date_parsing():
    from datetime import datetime

    assert parse_period(datetime(2026, 9, 4)) == date(2026, 9, 4)
    with pytest.raises(ValueError):
        parse_period("NOT-A-DATE")
    with pytest.raises(ValueError):
        parse_period(None)
    audit, _, _ = validate_gsec_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.all_fridays is True
    assert audit.min_date == date(2017, 10, 13)
    assert audit.max_date == date(2026, 9, 4)


# 5. numeric validity (zero failures, positive yields in plausible range)
def test_numeric_validity():
    audit, _, _ = validate_gsec_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.numeric_parsing_failures == 0
    assert audit.null_or_malformed_rows == 0
    assert audit.nonpositive_count == 0
    df = pd.read_csv(CANONICAL_PATH)
    assert (df["yield_pct"] > 0).all()
    assert df["yield_pct"].min() >= 5.0 and df["yield_pct"].max() <= 9.0


# 6. non-positive yield detection (synthetic)
def test_nonpositive_yield_detection(tmp_path: Path):
    import openpyxl

    bad = tmp_path / "gsec.xlsm"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Weekly"
    ws.append([])
    ws.append([])
    ws.append([])
    ws.append(["", "Period"] + [""] * 10 + [TARGET_SERIES])
    ws.append(["", __import__("datetime").datetime(2020, 1, 3), "", "", "", "", "", "", "", "", "", "", 0.0])
    wb.save(bad)
    audit, frame, excluded = validate_gsec_file(bad, bad.name)
    assert audit.nonpositive_count == 1
    assert len(excluded) == 1
    assert frame.empty


# 7. duplicate handling (none in artifact)
def test_duplicate_handling():
    audit, _, _ = validate_gsec_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.duplicate_dates_within_file == 0
    df = pd.read_csv(CANONICAL_PATH)
    assert df["observation_date"].duplicated().sum() == 0


# 8. temporal ordering + perfect weekly cadence (never resampled)
def test_temporal_ordering_and_cadence():
    audit, _, _ = validate_gsec_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.is_descending is True
    df = pd.read_csv(CANONICAL_PATH)
    dates = pd.to_datetime(df["observation_date"])
    assert dates.is_monotonic_increasing
    assert df["observation_date"].iloc[0] == "2017-10-13"
    assert df["observation_date"].iloc[-1] == "2026-09-04"
    assert (dates.dt.weekday == 4).all()
    assert set(dates.diff().dropna().dt.days) == {7}


# 9. canonical uniqueness + row counts
def test_canonical_uniqueness():
    df = pd.read_csv(CANONICAL_PATH)
    assert len(df) == 465
    assert df["observation_date"].nunique() == 465
    assert (df["tenor"] == TENOR).all()


# 10. provenance preservation
def test_provenance_preservation():
    df = pd.read_csv(CANONICAL_PATH)
    assert "source_files" in df.columns
    assert (df["source"] == "RBI").all()
    assert (df["source_files"] == RAW_NAME).all()
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.raw_paths == [f"data/raw/india/fixed_income/{RAW_NAME}"]
    assert manifest.raw_artifacts is not None and len(manifest.raw_artifacts) == 1
    assert manifest.raw_artifacts[0].sha256 == (
        "1072bfe9347c6c510c495d2d0894dc6e3931b23775a68faab5c74391f52e679d"
    )
    assert manifest.frequency == DataFrequency.WEEKLY


# 11. SHA-256 reproducibility
def test_sha256_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/market/rbi_gsec_10y_weekly.csv"
    )
    assert manifest.raw_artifacts
    for artifact in manifest.raw_artifacts:
        assert artifact.sha256 == manager.compute_sha256(artifact.path)


# 12. overlap/conflict behavior (single source: none; synthetic conflict rejected)
def test_overlap_conflict_rejection(tmp_path: Path):
    import datetime as dtmod
    import openpyxl

    files = discover_gsec_raw_files(RAW_DIR)
    frames = [validate_gsec_file(p, p.name)[1] for p in files]
    assert detect_overlaps(frames, [p.name for p in files]) == []

    def _wb(path: Path, day: dtmod.datetime, value: float) -> None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Weekly"
        ws.append([])
        ws.append([])
        ws.append([])
        ws.append(["", "Period"] + [""] * 10 + [TARGET_SERIES])
        ws.append(["", day, "", "", "", "", "", "", "", "", "", "", value])
        wb.save(path)

    first = tmp_path / "a.xlsx"
    second = tmp_path / "b.xlsx"
    _wb(first, dtmod.datetime(2020, 1, 3), 6.5)
    _wb(second, dtmod.datetime(2020, 1, 3), 9.9)
    frames2 = [
        validate_gsec_file(first, first.name)[1],
        validate_gsec_file(second, second.name)[1],
    ]
    overlaps = detect_overlaps(frames2, [first.name, second.name])
    assert len(overlaps) == 1 and overlaps[0].identical is False
    with pytest.raises(ValueError, match="Conflicting overlapping"):
        build_canonical(frames2, [first.name, second.name], overlaps)


# 13. leakage/information-boundary behavior
def test_leakage_information_boundary():
    df = pd.read_csv(CANONICAL_PATH)
    assert not any(
        any(token in str(col).lower() for token in ("future", "forward", "next_", "lead_"))
        for col in df.columns
    )
    report = LeakageAuditor().audit_all(price_df=df)
    assert report.is_clean
    cutoff = pd.Timestamp("2022-01-01")
    visible = df[pd.to_datetime(df["observation_date"]) <= cutoff]
    hidden = df[pd.to_datetime(df["observation_date"]) > cutoff]
    assert len(visible) > 0 and len(hidden) > 0
    assert pd.to_datetime(visible["observation_date"]).max() <= cutoff
    assert pd.to_datetime(hidden["observation_date"]).min() > cutoff


# 14. blocked eligibility
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.eligibility_status != EligibilityStatus.EXPERIMENT_ELIGIBLE


# 15. manifest bookkeeping arithmetic
def test_manifest_bookkeeping_arithmetic():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    params = manifest.processing_parameters
    assert params["total_raw_rows"] == 465
    assert params["excluded_invalid_rows"] == []
    assert params["duplicate_extra_rows_before_dedup"] == 0
    assert manifest.row_count == 465 == manifest.unique_date_count
