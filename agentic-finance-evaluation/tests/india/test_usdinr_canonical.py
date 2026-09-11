"""RBI USD/INR reference-rate acquisition/validation tests.

Covers the manually acquired RBI Reference Rate Archive export
(BankWise.xls, an HTML table exported as .xls). The raw file is immutable
evidence and is never modified by these tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.usdinr_canonicalize import (
    build_canonical,
    detect_overlaps,
    discover_usdinr_raw_files,
    header_matches_usdinr_schema,
    parse_rbi_date,
    read_rbi_table,
    validate_usdinr_file,
)
from src.india.leakage_audit import LeakageAuditor
from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    EligibilityStatus,
    ValidationStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "currency"
CANONICAL_PATH = PROJECT_ROOT / "data" / "processed" / "india" / "market" / "rbi_usd_inr_daily.csv"
MANIFEST_ID = "rbi_usd_inr_daily"
RAW_NAME = "BankWise.xls"


# 1. raw discovery
def test_raw_file_discovered():
    files = discover_usdinr_raw_files(RAW_DIR)
    assert [path.name for path in files] == [RAW_NAME]
    assert files[0].stat().st_size == 299998


# 2. container/header handling (HTML table as .xls, no xlrd needed)
def test_container_header_handling():
    rows = read_rbi_table(RAW_DIR / RAW_NAME)
    assert len(rows) == 5879
    assert header_matches_usdinr_schema([cell.strip() for cell in rows[0]])
    audit, _, _ = validate_usdinr_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.header_valid is True
    assert audit.header == ["Date", "USD (INR / 1 USD)"]


# 3. schema validation
def test_schema_validation():
    audit, frame, excluded = validate_usdinr_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.row_count == 5878
    assert audit.parsed_date_count == 5878
    assert audit.valid_row_count == 5878
    assert excluded == []
    assert set(frame.columns) >= {"date", "rate", "source_file"}


# 4. date parsing (DD/MM/YYYY)
def test_date_parsing():
    assert parse_rbi_date("11/09/2026") == date(2026, 9, 11)
    with pytest.raises(ValueError):
        parse_rbi_date("NOT-A-DATE")
    with pytest.raises(ValueError):
        parse_rbi_date("")


# 5. numeric validity (zero failures on real artifact)
def test_numeric_validity():
    audit, _, _ = validate_usdinr_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.numeric_parsing_failures == 0
    assert audit.null_or_malformed_rows == 0
    df = pd.read_csv(CANONICAL_PATH)
    assert (df["rate"] > 0).all()


# 6. non-positive rate detection (synthetic)
def test_nonpositive_rate_detection(tmp_path: Path):
    bad = tmp_path / "rates.xls"
    bad.write_text(
        "<table><tr><td>Date</td><td>USD (INR / 1 USD)</td></tr>"
        "<tr><td>01/01/2020</td><td>0</td></tr></table>",
        encoding="utf-8",
    )
    audit, frame, excluded = validate_usdinr_file(bad, bad.name)
    assert audit.nonpositive_count == 1
    assert len(excluded) == 1
    assert frame.empty


# 7. duplicate handling (none in artifact; synthetic within-file dupe)
def test_duplicate_handling(tmp_path: Path):
    audit, _, _ = validate_usdinr_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.duplicate_dates_within_file == 0
    dup = tmp_path / "dup.xls"
    dup.write_text(
        "<table><tr><td>Date</td><td>USD (INR / 1 USD)</td></tr>"
        "<tr><td>01/01/2020</td><td>71.5</td></tr>"
        "<tr><td>01/01/2020</td><td>71.5</td></tr></table>",
        encoding="utf-8",
    )
    audit2, _, _ = validate_usdinr_file(dup, dup.name)
    assert audit2.duplicate_dates_within_file == 1


# 8. temporal ordering (raw descending, canonical ascending)
def test_temporal_ordering():
    audit, _, _ = validate_usdinr_file(RAW_DIR / RAW_NAME, RAW_NAME)
    assert audit.is_descending is True
    df = pd.read_csv(CANONICAL_PATH)
    dates = pd.to_datetime(df["date"])
    assert dates.is_monotonic_increasing
    assert df["date"].iloc[0] == "1998-08-25"
    assert df["date"].iloc[-1] == "2026-09-11"


# 9. canonical uniqueness + documented source gap preserved (never filled)
def test_canonical_uniqueness_and_gap():
    df = pd.read_csv(CANONICAL_PATH)
    assert df["date"].duplicated().sum() == 0
    assert len(df) == 5878
    dates = pd.to_datetime(df["date"]).dt.date
    assert date(2019, 6, 3) not in set(dates)
    assert (dates.max() - dates.min()).days > len(df)


# 10. provenance preservation
def test_provenance_preservation():
    df = pd.read_csv(CANONICAL_PATH)
    assert "source_files" in df.columns
    assert (df["source"] == "RBI_REFERENCE_RATE").all()
    assert (df["is_reference_rate"] == True).all()  # noqa: E712
    assert (df["source_files"] == RAW_NAME).all()
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.raw_paths == [f"data/raw/india/currency/{RAW_NAME}"]
    assert manifest.raw_artifacts is not None and len(manifest.raw_artifacts) == 1
    assert manifest.raw_artifacts[0].sha256 == (
        "4b2b6cd815a53357ebdb3d72cc4728a80922fa5f57bafc26495d6dc3600a5068"
    )


# 11. SHA-256 reproducibility
def test_sha256_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/market/rbi_usd_inr_daily.csv"
    )
    assert manifest.raw_artifacts
    for artifact in manifest.raw_artifacts:
        assert artifact.sha256 == manager.compute_sha256(artifact.path)


# 12. overlap/conflict behavior (single file: none; synthetic conflict rejected)
def test_overlap_conflict_rejection(tmp_path: Path):
    files = discover_usdinr_raw_files(RAW_DIR)
    frames = [validate_usdinr_file(p, p.name)[1] for p in files]
    assert detect_overlaps(frames, [p.name for p in files]) == []
    first = tmp_path / "a.xls"
    second = tmp_path / "b.xls"
    row = "<tr><td>01/01/2020</td><td>{v}</td></tr>"
    header = "<table><tr><td>Date</td><td>USD (INR / 1 USD)</td></tr>"
    first.write_text(header + row.format(v="71.5") + "</table>", encoding="utf-8")
    second.write_text(header + row.format(v="99.9") + "</table>", encoding="utf-8")
    frames2 = [
        validate_usdinr_file(first, first.name)[1],
        validate_usdinr_file(second, second.name)[1],
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
    cutoff = pd.Timestamp("2020-01-01")
    visible = df[pd.to_datetime(df["date"]) <= cutoff]
    hidden = df[pd.to_datetime(df["date"]) > cutoff]
    assert len(visible) > 0 and len(hidden) > 0
    assert pd.to_datetime(visible["date"]).max() <= cutoff
    assert pd.to_datetime(hidden["date"]).min() > cutoff


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
    assert params["total_raw_rows"] == 5878
    assert params["excluded_invalid_rows"] == []
    assert params["duplicate_extra_rows_before_dedup"] == 0
    assert manifest.row_count == 5878 == manifest.unique_date_count
