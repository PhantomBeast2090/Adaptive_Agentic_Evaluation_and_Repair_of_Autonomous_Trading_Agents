"""India VIX multi-file acquisition/validation tests.

Mirrors tests/india/test_nifty_canonical.py for the manually acquired NSE
India VIX annual files. Raw files are immutable evidence and are never
modified by these tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.vix_canonicalize import (
    build_canonical,
    detect_overlaps,
    discover_vix_raw_files,
    header_matches_vix_schema,
    normalize_nse_header,
    parse_nse_date,
    validate_vix_file,
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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "india_vix"
CANONICAL_PATH = PROJECT_ROOT / "data" / "processed" / "india" / "market" / "nse_india_vix_daily.csv"
MANIFEST_ID = "nse_india_vix_daily"

VIX_HEADER = "Date ,Open ,High ,Low ,Close ,Prev. Close ,Change ,% Change "


def _write_vix_file(path: Path, rows: list[str]) -> None:
    path.write_text("\ufeff" + VIX_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


# 1. raw file discovery
def test_raw_files_discovered():
    files = discover_vix_raw_files(RAW_DIR)
    assert len(files) == 17
    assert all(path.name.startswith("hist_india_vix_") for path in files)
    assert files == sorted(files)


# 2. BOM/header handling
def test_bom_header_handling():
    assert header_matches_vix_schema(normalize_nse_header("\ufeff" + VIX_HEADER))
    for path in discover_vix_raw_files(RAW_DIR):
        audit, _, _ = validate_vix_file(path, path.name)
        assert audit.header_valid is True


# 3. NSE schema validation
def test_nse_schema_validation():
    for path in discover_vix_raw_files(RAW_DIR):
        audit, _, _ = validate_vix_file(path, path.name)
        assert audit.header == [
            "Date", "Open", "High", "Low", "Close",
            "Prev. Close", "Change", "% Change",
        ]
        assert audit.parsed_date_count == audit.row_count


# 4. date parsing
def test_date_parsing():
    assert parse_nse_date("03-NOV-2011") == date(2011, 11, 3)
    with pytest.raises(ValueError):
        parse_nse_date("NOT-A-DATE")
    with pytest.raises(ValueError):
        parse_nse_date("")


# 5. numeric validation
def test_numeric_validation(tmp_path: Path):
    bad = tmp_path / "hist_india_vix_bad.csv"
    _write_vix_file(bad, ["03-NOV-2011,ABC,26.18,24.42,24.66,24.89,-0.23,-0.92"])
    audit, frame, _ = validate_vix_file(bad, bad.name)
    assert audit.numeric_parsing_failures == 1
    assert frame.empty


# 6. OHLC validation
def test_ohlc_validation_rejected(tmp_path: Path):
    bad = tmp_path / "hist_india_vix_ohlc.csv"
    _write_vix_file(bad, ["22-AUG-2013,28.09,29.86,27.99,27.68,28.09,-0.41,-1.46"])
    audit, frame, excluded = validate_vix_file(bad, bad.name)
    assert audit.ohlc_violations == 1
    assert len(excluded) == 1
    assert frame.empty


# 7. negative/impossible-value detection
def test_negative_impossible_value_detection(tmp_path: Path):
    bad = tmp_path / "hist_india_vix_neg.csv"
    _write_vix_file(bad, ["12-FEB-2021,0,0,0,23.045,0,23.05,NaN"])
    audit, frame, excluded = validate_vix_file(bad, bad.name)
    assert audit.nonfinite_count == 1
    assert len(excluded) == 1
    assert frame.empty


# 8. within-file duplicate detection
def test_within_file_duplicate_detection(tmp_path: Path):
    dup = tmp_path / "hist_india_vix_dup.csv"
    _write_vix_file(dup, [
        "03-NOV-2011,24.89,26.18,24.42,24.66,24.89,-0.23,-0.92",
        "03-NOV-2011,24.89,26.18,24.42,24.66,24.89,-0.23,-0.92",
    ])
    audit, _, _ = validate_vix_file(dup, dup.name)
    assert audit.duplicate_dates_within_file == 1


# 9. cross-file overlap detection
def test_cross_file_overlap_detection():
    files = discover_vix_raw_files(RAW_DIR)
    frames = [validate_vix_file(p, p.name)[1] for p in files]
    overlaps = detect_overlaps(frames, [p.name for p in files])
    assert len(overlaps) == 12
    assert date(2011, 11, 3) in {item.overlap_date for item in overlaps}


# 10. identical-overlap deduplication
def test_identical_overlap_deduplication():
    files = discover_vix_raw_files(RAW_DIR)
    frames = [validate_vix_file(p, p.name)[1] for p in files]
    names = [p.name for p in files]
    overlaps = detect_overlaps(frames, names)
    assert all(item.identical for item in overlaps)
    total_valid = sum(len(frame) for frame in frames)
    canonical = build_canonical(frames, names, overlaps)
    assert len(canonical) == total_valid - len(overlaps)
    assert canonical["date"].nunique() == len(canonical)


# 11. conflicting-overlap rejection
def test_conflicting_overlap_rejection(tmp_path: Path):
    first = tmp_path / "hist_india_vix_a.csv"
    second = tmp_path / "hist_india_vix_b.csv"
    _write_vix_file(first, ["03-NOV-2011,24.89,26.18,24.42,24.66,24.89,-0.23,-0.92"])
    _write_vix_file(second, ["03-NOV-2011,99.0,99.0,99.0,99.0,99.0,0.0,0.0"])
    frames = [validate_vix_file(first, first.name)[1], validate_vix_file(second, second.name)[1]]
    overlaps = detect_overlaps(frames, [first.name, second.name])
    assert len(overlaps) == 1
    assert overlaps[0].identical is False
    with pytest.raises(ValueError, match="Conflicting overlapping"):
        build_canonical(frames, [first.name, second.name], overlaps)


# 12. canonical ordering
def test_canonical_ordering():
    df = pd.read_csv(CANONICAL_PATH)
    dates = pd.to_datetime(df["date"])
    assert dates.is_monotonic_increasing
    assert df["date"].iloc[0] == "2010-07-19"
    assert df["date"].iloc[-1] == "2026-09-11"


# 13. canonical uniqueness
def test_canonical_uniqueness():
    df = pd.read_csv(CANONICAL_PATH)
    assert df["date"].duplicated().sum() == 0
    assert len(df) == 4004


# 14. provenance preservation
def test_provenance_preservation():
    df = pd.read_csv(CANONICAL_PATH)
    assert "source_files" in df.columns
    assert (df["source"] == "NSE").all()
    assert df["source_files"].notna().all()
    assert df.loc[df["date"] == "2011-11-03", "source_files"].iloc[0].count(".csv") == 2
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.raw_paths is not None and len(manifest.raw_paths) == 17
    assert manifest.raw_artifacts is not None and len(manifest.raw_artifacts) == 17


# 15. SHA-256 reproducibility
def test_sha256_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/market/nse_india_vix_daily.csv"
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


# 17. blocked eligibility when historical calendar/common intersection is unavailable
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.eligibility_status != EligibilityStatus.EXPERIMENT_ELIGIBLE
