"""NIFTY 50 multi-file acquisition/validation tests.

Covers the 16 required cases for the manual NSE annual-file acquisition:
discovery, overlap handling, schema/numeric/OHLC/negativity checks,
ordering, deduplication, multi-artifact manifest provenance, staleness,
blocked eligibility, and no future-information exposure.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.nifty_canonicalize import (
    build_canonical,
    detect_overlaps,
    discover_nifty_raw_files,
    header_matches_nse_schema,
    normalize_nse_header,
    parse_nse_date,
    validate_nse_file,
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
CANONICAL_PATH = PROJECT_ROOT / "data" / "processed" / "india" / "market" / "nse_nifty_50_daily.csv"
MANIFEST_ID = "nse_nifty_50_daily"

NSE_HEADER = "Date ,Open ,High ,Low ,Close ,Shares Traded ,Turnover (₹ Cr)"


def _write_nse_file(path: Path, rows: list[str]) -> None:
    path.write_text("\ufeff" + NSE_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


# 1. multiple raw files discovered
def test_multiple_raw_files_discovered():
    files = discover_nifty_raw_files(RAW_DIR)
    assert len(files) == 29
    assert all(path.name.startswith("NIFTY 50-") for path in files)
    assert files == sorted(files)


# 2. annual boundary overlap detection
def test_annual_boundary_overlap_detection():
    audits_frames = [validate_nse_file(p, p.name) for p in discover_nifty_raw_files(RAW_DIR)]
    frames = [frame for _, frame in audits_frames]
    names = [p.name for p in discover_nifty_raw_files(RAW_DIR)]
    overlaps = detect_overlaps(frames, names)
    assert len(overlaps) == 20
    assert date(1999, 11, 3) in {item.overlap_date for item in overlaps}
    for item in overlaps:
        assert len(item.files) == 2


# 3. identical boundary duplicates deduplicated
def test_identical_boundary_duplicates_deduplicated():
    files = discover_nifty_raw_files(RAW_DIR)
    frames = [validate_nse_file(p, p.name)[1] for p in files]
    names = [p.name for p in files]
    overlaps = detect_overlaps(frames, names)
    assert all(item.identical for item in overlaps)
    total_raw = sum(len(frame) for frame in frames)
    canonical = build_canonical(frames, names, overlaps)
    assert len(canonical) == total_raw - len(overlaps)
    assert canonical["date"].nunique() == len(canonical)


# 4. conflicting overlap detected
def test_conflicting_overlap_detected(tmp_path: Path):
    first = tmp_path / "NIFTY 50-a.csv"
    second = tmp_path / "NIFTY 50-b.csv"
    _write_nse_file(first, ["03-NOV-1999,1332.7,1353.55,1303.25,1326.4,51551841,1914.47"])
    _write_nse_file(second, ["03-NOV-1999,9999.0,9999.0,9999.0,9999.0,1,1.0"])
    frames = [validate_nse_file(first, first.name)[1], validate_nse_file(second, second.name)[1]]
    overlaps = detect_overlaps(frames, [first.name, second.name])
    assert len(overlaps) == 1
    assert overlaps[0].identical is False
    with pytest.raises(ValueError, match="Conflicting overlapping"):
        build_canonical(frames, [first.name, second.name], overlaps)


# 5. schema validation
def test_nse_schema_validation():
    assert header_matches_nse_schema(normalize_nse_header("\ufeff" + NSE_HEADER))
    assert parse_nse_date("03-NOV-1999") == date(1999, 11, 3)
    for path in discover_nifty_raw_files(RAW_DIR):
        audit, _ = validate_nse_file(path, path.name)
        assert audit.header_valid is True
        assert audit.parsed_date_count == audit.row_count


# 6. malformed dates rejected
def test_malformed_dates_rejected(tmp_path: Path):
    bad = tmp_path / "NIFTY 50-bad.csv"
    _write_nse_file(bad, ["NOT-A-DATE,1,2,1,1.5,100,1.0", "03-NOV-1999,1,2,1,1.5,100,1.0"])
    audit, frame = validate_nse_file(bad, bad.name)
    assert audit.null_or_malformed_rows == 1
    assert len(frame) == 1


# 7. numeric-field validation
def test_numeric_field_validation(tmp_path: Path):
    bad = tmp_path / "NIFTY 50-num.csv"
    _write_nse_file(bad, ["03-NOV-1999,ABC,1353.55,1303.25,1326.4,51551841,1914.47"])
    audit, frame = validate_nse_file(bad, bad.name)
    assert audit.numeric_parsing_failures == 1
    assert frame.empty


# 8. OHLC consistency
def test_ohlc_consistency_rejected(tmp_path: Path):
    bad = tmp_path / "NIFTY 50-ohlc.csv"
    # High (1.0) below Open/Close -> impossible.
    _write_nse_file(bad, ["03-NOV-1999,100.0,1.0,90.0,95.0,100,1.0"])
    audit, _ = validate_nse_file(bad, bad.name)
    assert audit.ohlc_violations == 1


# 9. negative volume/turnover rejection
def test_negative_volume_turnover_rejected(tmp_path: Path):
    bad = tmp_path / "NIFTY 50-neg.csv"
    _write_nse_file(bad, ["03-NOV-1999,100.0,110.0,90.0,105.0,-5,1.0"])
    audit, _ = validate_nse_file(bad, bad.name)
    assert audit.negative_volume_count == 1
    bad2 = tmp_path / "NIFTY 50-neg2.csv"
    _write_nse_file(bad2, ["03-NOV-1999,100.0,110.0,90.0,105.0,100,-2.0"])
    audit2, _ = validate_nse_file(bad2, bad2.name)
    assert audit2.negative_turnover_count == 1


# 10. canonical chronological ordering
def test_canonical_chronological_ordering():
    df = pd.read_csv(CANONICAL_PATH)
    dates = pd.to_datetime(df["date"])
    assert dates.is_monotonic_increasing
    assert df["date"].iloc[0] == "1997-11-03"
    assert df["date"].iloc[-1] == "2026-09-11"


# 11. duplicate-free canonical dates
def test_duplicate_free_canonical_dates():
    df = pd.read_csv(CANONICAL_PATH)
    assert df["date"].duplicated().sum() == 0
    assert len(df) == 7183


# 12. manifest records multiple raw artifacts
def test_manifest_records_multiple_raw_artifacts():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.raw_paths is not None and len(manifest.raw_paths) == 29
    assert manifest.raw_artifacts is not None and len(manifest.raw_artifacts) == 29
    assert manifest.raw_path is None
    assert manifest.processed_path == "data/processed/india/market/nse_nifty_50_daily.csv"
    assert manifest.duplicate_count == 0
    assert manifest.row_count == 7183


# 13. SHA-256 provenance
def test_sha256_provenance_matches_artifacts():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/market/nse_nifty_50_daily.csv"
    )
    assert manifest.raw_artifacts
    for artifact in manifest.raw_artifacts:
        assert artifact.sha256 == manager.compute_sha256(artifact.path)
    assert not manifest.raw_artifacts[0].sha256 == "0" * 64


# 14. stale-manifest detection
def test_stale_manifest_detection(tmp_path: Path):
    raw = tmp_path / "raw.csv"
    raw.write_text("date,close\n2024-01-01,100\n")
    manager = ManifestManager(str(tmp_path))
    manifest = manager.create_manifest(
        dataset_id="stale_multi",
        tier=DataTier.A,
        asset_class="index",
        variable="X",
        source_institution="NSE",
        source_url="https://example.test/x.csv",
        frequency=DataFrequency.DAILY,
        raw_paths=["raw.csv"],
        raw_artifacts=[{"path": "raw.csv", "sha256": manager.compute_sha256("raw.csv")}],
        earliest_observation="2024-01-01",
        latest_observation="2024-01-01",
        row_count=1,
        acquisition_status=AcquisitionStatus.ACQUIRED,
        validation_status=ValidationStatus.PASSED,
    )
    raw.write_text("date,close\n2024-01-01,999\n")
    errors = manager.validate_manifest(manifest)
    assert any("SHA-256 mismatch" in error for error in errors)


# 15. experiment eligibility remains blocked when dependencies are missing
def test_experiment_eligibility_remains_blocked():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.eligibility_status != EligibilityStatus.EXPERIMENT_ELIGIBLE


# 16. no future-information exposure
def test_no_future_information_exposure():
    df = pd.read_csv(CANONICAL_PATH)
    assert not any(
        any(token in str(col).lower() for token in ("future", "forward", "next_", "lead_"))
        for col in df.columns
    )
    report = LeakageAuditor().audit_all(price_df=df)
    assert report.is_clean
    # Information-boundary model: at simulated time t only dates <= t are visible.
    cutoff = pd.Timestamp("2020-01-01")
    visible = df[pd.to_datetime(df["date"]) <= cutoff]
    hidden = df[pd.to_datetime(df["date"]) > cutoff]
    assert len(visible) > 0 and len(hidden) > 0
    assert pd.to_datetime(visible["date"]).max() <= cutoff
    assert pd.to_datetime(hidden["date"]).min() > cutoff
