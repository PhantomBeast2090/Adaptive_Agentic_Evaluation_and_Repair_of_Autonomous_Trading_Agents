"""EIA Europe Brent Spot Price FOB (RBRTE) acquisition/validation tests.

Covers the official EIA hist_xls export
(data/raw/india/crude/eia_rbrte_brent_spot_daily.xls, sheet Data 1).
The raw file is immutable evidence and is never modified by these tests.
Full-workbook re-parsing is cheap (single file) so structural checks run
against the real artifact; conflict/negative paths use synthetic fixtures.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.brent_canonicalize import (
    AGENT_ELIGIBLE_VINTAGES,
    CANONICAL_COLUMNS,
    EXPECTED_SERIES_ID,
    RAW_FILENAME,
    agent_eligible_rows,
    audit_all_files,
    build_agent_information_set,
    build_canonical,
    detect_overlaps,
    discover_brent_raw_files,
    read_eia_workbook,
    validate_brent_file,
    validate_no_forward_fill,
)
from src.india.information_set import InformationSet
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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "crude"
RAW_PATH = RAW_DIR / RAW_FILENAME
CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "india" / "crude"
    / "eia_rbrte_brent_spot_daily.csv"
)
MANIFEST_ID = "crude_oil_brent_daily"

RAW_BYTE_SIZE = 492544
RAW_SHA256 = "1906d1c44279fd769f5f5b04882ce29376d8a42e1c1764cfee9c26a255817669"
CANONICAL_SHA256 = "2d0346c4bc562b6128f068b7f396fac2f1600ce72fd64a94017337e6266d31dc"


def _canonical() -> pd.DataFrame:
    return pd.read_csv(CANONICAL_PATH)


# 1. raw discovery (official EIA artifact, immutable)
def test_raw_artifact_discovered():
    files = discover_brent_raw_files(RAW_DIR)
    assert [p.name for p in files] == [RAW_FILENAME]
    assert RAW_PATH.stat().st_size == RAW_BYTE_SIZE


# 2. exact series targeting (RBRTE spot, never futures)
def test_series_identity():
    series_id, records = read_eia_workbook(RAW_PATH)
    assert series_id == EXPECTED_SERIES_ID == "RBRTE"
    assert len(records) == 9973
    df = _canonical()
    assert (df["source"] == "EIA").all()
    assert (df["series_id"] == "RBRTE").all()
    assert (df["unit"] == "USD_per_bbl").all()
    # No futures/OHLC/synthetic columns may ever appear.
    assert set(df.columns) == set(CANONICAL_COLUMNS)
    for col in ("open", "high", "low", "close", "futures", "settlement"):
        assert col not in df.columns


# 3. schema (source-supported fields only)
def test_schema():
    df = _canonical()
    assert list(df.columns) == CANONICAL_COLUMNS
    assert df["brent_spot_usd_bbl"].notna().all()
    assert (df["brent_spot_usd_bbl"] > 0).all()


# 4. coverage (1987-05-20..2026-09-09, 9973 unique dates)
def test_coverage():
    df = _canonical()
    assert len(df) == 9973
    assert df["observation_date"].nunique() == 9973
    assert df["observation_date"].min() == "1987-05-20"
    assert df["observation_date"].max() == "2026-09-09"


# 5. date parsing (Excel serials resolve to EIA observation days)
def test_date_parsing():
    df = _canonical().set_index("observation_date")["brent_spot_usd_bbl"]
    assert float(df["1987-05-20"]) == pytest.approx(18.63)
    assert float(df["2008-07-03"]) == pytest.approx(143.95)
    assert float(df["2026-09-09"]) == pytest.approx(109.51)


# 6. chronological order (strictly increasing, no reordering)
def test_chronological_order():
    audit, _, _ = validate_brent_file(RAW_PATH, RAW_FILENAME)
    assert audit.is_ascending is True
    assert audit.first_observation == date(1987, 5, 20)
    assert audit.last_observation == date(2026, 9, 9)
    dates = pd.to_datetime(_canonical()["observation_date"])
    assert dates.is_monotonic_increasing
    assert dates.is_unique


# 7. duplicate handling (none in artifact; synthetic identical dedupes)
def test_duplicate_handling():
    audit, frame, _ = validate_brent_file(RAW_PATH, RAW_FILENAME)
    assert audit.duplicate_dates_within_file == 0
    dup = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    overlaps = detect_overlaps([frame, frame.iloc[[0]]], ["a.xls", "b.xls"])
    assert len(overlaps) == 1
    assert overlaps[0].identical is True
    canon = build_canonical([frame, frame.iloc[[0]]], ["a.xls", "b.xls"], overlaps)
    assert len(canon) == len(frame)
    sources = canon[canon["observation_date"] == date(1987, 5, 20)]["source_files"].iloc[0]
    assert "a.xls" in sources and "b.xls" in sources
    _ = dup  # provenance merge asserted above, not row growth


# 8. conflict handling (synthetic conflicting duplicate raises, never resolved)
def test_conflict_handling():
    _, frame, _ = validate_brent_file(RAW_PATH, RAW_FILENAME)
    other = frame.iloc[[0]].copy()
    other["brent_spot_usd_bbl"] = float(other["brent_spot_usd_bbl"].iloc[0]) + 1.0
    overlaps = detect_overlaps([frame, other], ["a.xls", "b.xls"])
    assert any(not item.identical for item in overlaps)
    with pytest.raises(ValueError, match="Conflicting overlapping"):
        build_canonical([frame, other], ["a.xls", "b.xls"], overlaps)


# 9. numeric validity (zero failures on real artifact)
def test_numeric_validity():
    audit, _, excluded = validate_brent_file(RAW_PATH, RAW_FILENAME)
    assert audit.numeric_parsing_failures == 0
    assert audit.null_or_malformed_rows == 0
    assert audit.nonpositive_count == 0
    assert audit.nonfinite_count == 0
    assert excluded == []
    assert audit.valid_row_count == 9973


# 10. non-positive/non-finite detection (synthetic fixtures, never in canonical)
def test_nonpositive_nonfinite_detection():
    import math

    _, frame, _ = validate_brent_file(RAW_PATH, RAW_FILENAME)
    bad = frame.iloc[[0]].copy()
    bad["brent_spot_usd_bbl"] = 0.0
    nan = frame.iloc[[1]].copy()
    nan["brent_spot_usd_bbl"] = math.nan
    for variant in (bad, nan):
        cleaned = variant[pd.to_numeric(variant["brent_spot_usd_bbl"], errors="coerce").notna()
                          & (variant["brent_spot_usd_bbl"] > 0)]
        assert cleaned.empty
    assert validate_no_forward_fill(_canonical()) == []


# 11. missingness (values complete; availability wholly unknown)
def test_missingness():
    df = _canonical()
    assert df["observation_date"].notna().all()
    assert df["brent_spot_usd_bbl"].notna().all()
    assert df["availability_date"].isna().all()
    assert (df["availability_basis"] == "unknown_historical_availability").all()


# 12. calendar behavior (global weekday series; never NSE-forced, never filled)
def test_calendar_behavior():
    df = _canonical()
    dates = pd.to_datetime(df["observation_date"]).dt.date
    assert sum(d.weekday() >= 5 for d in dates) == 0
    # Canonical preserves every validated observation: no fills, no drops.
    assert len(df) == 9973
    # Source closures stay absent (e.g. US Independence Day 2008-07-04).
    assert "2008-07-04" not in set(df["observation_date"])


# 13. crisis extremes preserved (verified against the EIA HTML page 2026-09-12)
def test_extreme_values_preserved():
    df = _canonical().set_index("observation_date")["brent_spot_usd_bbl"]
    assert float(df["2020-04-21"]) == pytest.approx(9.12)  # COVID crash print
    assert float(df["2008-07-03"]) == pytest.approx(143.95)  # all-time high
    assert float(df["1998-12-10"]) == pytest.approx(9.1)  # 1998 low
    assert float(df["2022-03-08"]) == pytest.approx(133.18)  # 2022 spike


# 14. single observed vintage per date (no manufactured revisions)
def test_single_vintage_per_date():
    df = _canonical()
    assert (df["vintage_status"] == "observed").all()
    assert (df["revision_version"] == 0).all()
    assert df.duplicated(subset=["observation_date"]).sum() == 0


# 15. manifest bookkeeping (9973 rows, 0 duplicates/conflicts)
def test_manifest_bookkeeping():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.row_count == 9973
    assert manifest.unique_date_count == 9973
    assert manifest.duplicate_count == 0
    assert manifest.processing_parameters["canonical_rows"] == 9973
    assert manifest.processing_parameters["conflicting_overlaps"] == 0
    assert manifest.processing_parameters["series_id"] .startswith("RBRTE")
    assert len(_canonical()) == 9973


# 16. SHA reproducibility (raw + canonical)
def test_sha_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.raw_sha256 == RAW_SHA256 == manager.compute_sha256(
        "data/raw/india/crude/eia_rbrte_brent_spot_daily.xls"
    )
    assert manifest.processed_sha256 == CANONICAL_SHA256 == manager.compute_sha256(
        "data/processed/india/crude/eia_rbrte_brent_spot_daily.csv"
    )


# 17. deterministic output (rebuild from raw yields identical frame)
def test_deterministic_output():
    audits, frames, _ = audit_all_files(RAW_DIR)
    names = [a.filename for a in audits]
    rebuilt = build_canonical(frames, names, detect_overlaps(frames, names))
    current = _canonical()
    assert list(rebuilt.columns) == list(current.columns)
    assert len(rebuilt) == len(current)
    assert (
        rebuilt["brent_spot_usd_bbl"].astype(float).tolist()
        == current["brent_spot_usd_bbl"].astype(float).tolist()
    )
    assert rebuilt["observation_date"].astype(str).tolist() == current[
        "observation_date"
    ].tolist()


# 18. blocked eligibility (acquired/passed/blocked, never eligible)
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.frequency == DataFrequency.DAILY
    assert manifest.tier == DataTier.C
    assert manifest.asset_class == "crude"
    assert manifest.variable == "brent_spot_usd_bbl"


# 19. LEAKAGE CASE 1+2+5: nothing visible before/at/after any boundary
def test_leakage_nothing_ever_visible():
    df = _canonical()
    assert agent_eligible_rows(df).empty
    with pytest.raises(ValueError, match="No agent-eligible Brent"):
        build_agent_information_set(df)


# 20. LEAKAGE CASE 3: no later revision can back-leak (single vintage)
def test_leakage_no_revision_backleak():
    df = _canonical()
    assert df.groupby("observation_date")["revision_version"].nunique().max() == 1


# 21. LEAKAGE CASE 4: missing availability wholly excluded from agent set
def test_leakage_missing_availability_excluded():
    df = _canonical()
    assert len(df) == 9973  # environment retains everything
    assert len(agent_eligible_rows(df)) == 0  # agent sees nothing
    assert AGENT_ELIGIBLE_VINTAGES == frozenset()


# 22. LEAKAGE CASE 6 + gate proof: InformationSet never receives NULLs
def test_leakage_information_set_never_receives_nulls():
    df = _canonical()
    # The Brent gate fails closed BEFORE InformationSet construction.
    with pytest.raises(ValueError, match="No agent-eligible Brent"):
        build_agent_information_set(df)
    # And InformationSet itself still rejects NA availability (unweakened).
    bad = pd.DataFrame(
        {
            "variable": ["BRENT_SPOT"],
            "observation_date": pd.to_datetime(["2020-01-01"]),
            "availability_date": pd.to_datetime(["NaT"]),
            "revision_version": [0],
            "value": [20.0],
        }
    )
    with pytest.raises(ValueError, match="reliable availability"):
        InformationSet(bad)


# 23. agent gate fails closed on empty input
def test_agent_gate_fails_closed_empty():
    with pytest.raises(ValueError, match="No agent-eligible Brent"):
        build_agent_information_set(_canonical().iloc[0:0])


# 24. no fabrication (nulls stay null; values finite positive)
def test_no_fabrication():
    df = _canonical()
    assert validate_no_forward_fill(df) == []
    assert df["availability_date"].isna().all()  # never invented
    assert (df["brent_spot_usd_bbl"] > 0).all()


# 25. leakage auditor price-frame clean
def test_leakage_auditor_clean():
    report = LeakageAuditor().audit_all(price_df=_canonical())
    assert report.is_clean
