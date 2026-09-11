"""NIFTY 500 multi-file acquisition/validation tests.

Mirrors tests/india/test_nifty_canonical.py and test_vix_canonical.py for
the manually acquired NSE NIFTY 500 annual files colocated under
data/raw/india/indices/. Raw files are immutable evidence and are never
modified by these tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.nifty500_canonicalize import (
    EXPECTED_INDEX_NAME,
    build_canonical,
    detect_overlaps,
    discover_nifty500_raw_files,
    header_matches_nifty500_schema,
    parse_nse_date,
    validate_nifty500_file,
)
from src.india.leakage_audit import LeakageAuditor
from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    DataTier,
    EligibilityStatus,
    ValidationStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "indices"
CANONICAL_PATH = PROJECT_ROOT / "data" / "processed" / "india" / "market" / "nse_nifty_500_daily.csv"
MANIFEST_ID = "nse_nifty_500_daily"


def _write_n500_file(path: Path, rows: list[str]) -> None:
    path.write_text(
        '"Index Name","Date","Open","High","Low","Close"\n' + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


# 1. raw file discovery (NIFTY 500 only, colocated with NIFTY 50)
def test_raw_files_discovered():
    files = discover_nifty500_raw_files(RAW_DIR)
    assert len(files) == 30
    assert all(path.name.startswith("NIFTY 500_Historical_PR_") for path in files)
    assert files == sorted(files)
    assert not any(path.name.startswith("NIFTY 50-") for path in files)


# 2. BOM/header handling
def test_bom_header_handling():
    assert header_matches_nifty500_schema(
        ["Index Name", "Date", "Open", "High", "Low", "Close"]
    )
    for path in discover_nifty500_raw_files(RAW_DIR):
        audit, _, _ = validate_nifty500_file(path, path.name)
        assert audit.header_valid is True
        assert audit.has_bom is False


# 3. schema validation + index-name verification
def test_nse_schema_validation():
    for path in discover_nifty500_raw_files(RAW_DIR):
        audit, _, _ = validate_nifty500_file(path, path.name)
        assert audit.header == ["Index Name", "Date", "Open", "High", "Low", "Close"]
        assert audit.index_names_observed == [EXPECTED_INDEX_NAME]


# 4. date parsing
def test_date_parsing():
    assert parse_nse_date("01 Nov 2005") == date(2005, 11, 1)
    with pytest.raises(ValueError):
        parse_nse_date("NOT-A-DATE")
    with pytest.raises(ValueError):
        parse_nse_date("")


# 5. numeric validation (dash placeholders rejected)
def test_numeric_validation(tmp_path: Path):
    bad = tmp_path / "NIFTY 500_Historical_PR_test.csv"
    _write_n500_file(bad, ['"NIFTY 500","04 Mar 1997","-","-","-","730.01"'])
    audit, frame, excluded = validate_nifty500_file(bad, bad.name)
    assert audit.numeric_parsing_failures == 1
    assert len(excluded) == 1
    assert frame.empty


# 6. OHLC validation
def test_ohlc_validation_rejected(tmp_path: Path):
    bad = tmp_path / "NIFTY 500_Historical_PR_test.csv"
    _write_n500_file(bad, ['"NIFTY 500","30 Dec 2002","771.90","765.95","770.85","770.85"'])
    audit, frame, excluded = validate_nifty500_file(bad, bad.name)
    assert audit.ohlc_violations == 1
    assert len(excluded) == 1
    assert frame.empty


# 7. negative/impossible-value detection
def test_negative_impossible_value_detection(tmp_path: Path):
    bad = tmp_path / "NIFTY 500_Historical_PR_test.csv"
    _write_n500_file(bad, ['"NIFTY 500","01 Jan 2000","0","100.0","90.0","95.0"'])
    audit, frame, excluded = validate_nifty500_file(bad, bad.name)
    assert audit.negative_or_nonpositive_count == 1
    assert len(excluded) == 1
    assert frame.empty


# 8. within-file duplicate detection
def test_within_file_duplicate_detection(tmp_path: Path):
    dup = tmp_path / "NIFTY 500_Historical_PR_test.csv"
    _write_n500_file(dup, [
        '"NIFTY 500","01 Nov 2005","2096.65","2096.65","2079.45","2084.65"',
        '"NIFTY 500","01 Nov 2005","2096.65","2096.65","2079.45","2084.65"',
    ])
    audit, _, _ = validate_nifty500_file(dup, dup.name)
    assert audit.duplicate_dates_within_file == 1


# 9. cross-file overlap detection
def test_cross_file_overlap_detection():
    files = discover_nifty500_raw_files(RAW_DIR)
    frames = [validate_nifty500_file(p, p.name)[1] for p in files]
    overlaps = detect_overlaps(frames, [p.name for p in files])
    assert len(overlaps) == 21
    assert date(1997, 11, 3) in {item.overlap_date for item in overlaps}


# 10. identical-overlap deduplication
def test_identical_overlap_deduplication():
    files = discover_nifty500_raw_files(RAW_DIR)
    frames = [validate_nifty500_file(p, p.name)[1] for p in files]
    names = [p.name for p in files]
    overlaps = detect_overlaps(frames, names)
    assert all(item.identical for item in overlaps)
    total_valid = sum(len(frame) for frame in frames)
    canonical = build_canonical(frames, names, overlaps)
    assert len(canonical) == total_valid - len(overlaps)
    assert canonical["date"].nunique() == len(canonical)


# 11. conflicting-overlap rejection
def test_conflicting_overlap_rejection(tmp_path: Path):
    first = tmp_path / "NIFTY 500_Historical_PR_a.csv"
    second = tmp_path / "NIFTY 500_Historical_PR_b.csv"
    _write_n500_file(first, ['"NIFTY 500","01 Nov 2005","2096.65","2096.65","2079.45","2084.65"'])
    _write_n500_file(second, ['"NIFTY 500","01 Nov 2005","9999.0","9999.0","9999.0","9999.0"'])
    frames = [validate_nifty500_file(first, first.name)[1], validate_nifty500_file(second, second.name)[1]]
    overlaps = detect_overlaps(frames, [first.name, second.name])
    assert len(overlaps) == 1
    assert overlaps[0].identical is False
    with pytest.raises(ValueError, match="Conflicting overlapping"):
        build_canonical(frames, [first.name, second.name], overlaps)


# 12. canonical chronological ordering
def test_canonical_ordering():
    df = pd.read_csv(CANONICAL_PATH)
    dates = pd.to_datetime(df["date"])
    assert dates.is_monotonic_increasing
    assert df["date"].iloc[0] == "1996-11-04"
    assert df["date"].iloc[-1] == "2026-09-11"


# 13. canonical uniqueness (+ no fabricated volume)
def test_canonical_uniqueness():
    df = pd.read_csv(CANONICAL_PATH)
    assert df["date"].duplicated().sum() == 0
    assert len(df) == 7413
    assert "volume" not in df.columns
    assert "turnover" not in df.columns


# 14. provenance preservation
def test_provenance_preservation():
    df = pd.read_csv(CANONICAL_PATH)
    assert "source_files" in df.columns
    assert (df["source"] == "NSE").all()
    assert (df["index_name"] == "NIFTY 500").all()
    assert df["source_files"].notna().all()
    assert df.loc[df["date"] == "1997-11-03", "source_files"].iloc[0].count(".csv") == 2
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.raw_paths is not None and len(manifest.raw_paths) == 30
    assert manifest.raw_artifacts is not None and len(manifest.raw_artifacts) == 30


# 15. SHA-256 reproducibility
def test_sha256_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/market/nse_nifty_500_daily.csv"
    )
    assert manifest.raw_artifacts
    for artifact in manifest.raw_artifacts:
        assert artifact.sha256 == manager.compute_sha256(artifact.path)


# 16. leakage/information-boundary behavior
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


# 18. manifest bookkeeping arithmetic: raw - excluded - dupes = canonical
def test_manifest_bookkeeping_arithmetic():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    params = manifest.processing_parameters
    assert params["total_raw_rows"] == 7442
    assert len(params["excluded_invalid_rows"]) == 8
    assert params["duplicate_extra_rows_before_dedup"] == 21
    assert params["identical_boundary_duplicates_deduped"] == 21
    assert (
        params["total_raw_rows"]
        - len(params["excluded_invalid_rows"])
        - params["duplicate_extra_rows_before_dedup"]
        == manifest.row_count
        == 7413
    )


# 17. blocked eligibility
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.eligibility_status != EligibilityStatus.EXPERIMENT_ELIGIBLE
