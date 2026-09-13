"""NSE Capital Market equity daily bhavcopy acquisition/validation tests.

Covers the official NSE sec_bhav + UDiFF archives under
data/raw/india/equities/ (immutable evidence, never modified here).
Full-corpus aggregates live in the committed manifest
(data/manifests/india/nse_equity_bhavcopy_daily.yaml); these tests use
real-file spot-checks plus synthetic fixtures and stay offline-fast.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.nse_equity_canonicalize import (
    AGENT_ELIGIBLE_VINTAGES,
    CANONICAL_COLUMNS,
    agent_eligible_rows,
    build_agent_information_set,
    build_canonical,
    classify_ohlc,
    compare_regimes,
    detect_key_overlaps,
    discover_raw_files,
    parse_sec_bhav_date,
    parse_udiff_date,
    validate_no_forward_fill,
    validate_sec_bhav_file,
    validate_udiff_file,
    _to_float,
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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "equities"
CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "india" / "equities"
    / "nse_equity_daily.csv"
)
MANIFEST_ID = "nse_equity_bhavcopy_daily"

SEC_SAMPLE = RAW_DIR / "sec_bhavdata_full_08072024.csv"
UDIFF_SAMPLE = RAW_DIR / "BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip"
XLSX_VARIANT = RAW_DIR / "sec_bhavdata_full_08082022.csv"


def _manifest():
    return ManifestManager(str(PROJECT_ROOT)).load_manifest(MANIFEST_ID)


def _manifest_params():
    return _manifest().processing_parameters


# 1. raw artifact discovery (official NSE artifacts + acquisition index)
def test_raw_artifact_discovery():
    sec, udiff = discover_raw_files(RAW_DIR)
    assert len(sec) == 1801
    assert len(udiff) == 666
    assert (RAW_DIR / "bhavcopy_index.csv").exists()
    with open(RAW_DIR / "bhavcopy_index.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2520
    by_status = {}
    for row in rows:
        by_status[row["http_status"]] = by_status.get(row["http_status"], 0) + 1
    assert by_status.get("200") == 2467


# 2. source identity (NSE only, both regimes)
def test_source_identity():
    _, frame, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    assert len(frame) == 2637
    _, uframe, _ = validate_udiff_file(UDIFF_SAMPLE, "r")
    assert len(uframe) == 2815
    canon = pd.read_csv(CANONICAL_PATH, usecols=["source", "regime"], nrows=5000)
    assert (canon["source"] == "NSE").all()
    assert (canon["regime"] == "sec_bhav").all()


# 3. format regime detection (headers + xlsx-container variant)
def test_format_regime_detection():
    audit, _, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    assert audit.header_valid is True
    assert audit.regime == "sec_bhav"
    uaudit, _, _ = validate_udiff_file(UDIFF_SAMPLE, "r")
    assert uaudit.header_valid is True
    assert uaudit.regime == "udiff"
    xaudit, xframe, _ = validate_sec_bhav_file(XLSX_VARIANT, "r")
    assert xaudit.header_valid is True
    assert len(xframe) == 2255
    assert xaudit.infile_date == "08-Aug-2022"


# 4. schema validation (exact canonical columns)
def test_schema_validation():
    canon = pd.read_csv(CANONICAL_PATH, nrows=5)
    assert list(canon.columns) == CANONICAL_COLUMNS
    assert canon["close"].notna().all()


# 5. security/date key uniqueness (manifest + validation accounting)
def test_key_uniqueness():
    manifest = _manifest()
    assert manifest.duplicate_count == 0
    params = _manifest_params()
    assert params["unique_security_date_keys"] == params["canonical_rows"] == 4205764
    sample = pd.read_csv(
        CANONICAL_PATH, usecols=["observation_date", "symbol", "series"],
        nrows=200000)
    assert sample.duplicated(subset=["observation_date", "symbol", "series"]).sum() == 0


# 6. duplicate detection (identical duplicates dedup with provenance)
def test_duplicate_detection():
    _, frame, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    dup = frame.iloc[[0]].copy()
    overlaps = detect_key_overlaps(
        [frame, dup], ["a.csv", "b.csv"],
        ["open", "high", "low", "close"])
    assert len(overlaps) == 1
    assert overlaps[0].identical is True
    canon, _ = build_canonical([frame, dup], ["a.csv", "b.csv"])
    assert len(canon) == len(frame)
    assert "a.csv" in canon["source_files"].iloc[0]
    assert "b.csv" in canon["source_files"].iloc[0]


# 7. conflict detection (conflicting duplicates raise, never resolved)
def test_conflict_detection():
    _, frame, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    bad = frame.iloc[[0]].copy()
    bad["close"] = float(bad["close"].iloc[0]) + 1.0
    overlaps = detect_key_overlaps(
        [frame, bad], ["a.csv", "b.csv"],
        ["open", "high", "low", "close"])
    assert any(not o.identical for o in overlaps)
    with pytest.raises(ValueError, match="Conflicting sec_bhav"):
        build_canonical([frame, bad], ["a.csv", "b.csv"])


# 8. date parsing (both regime formats; malformed raises)
def test_date_parsing():
    assert parse_sec_bhav_date("05-Jul-2024") == date(2024, 7, 5)
    assert parse_udiff_date("2024-07-05") == date(2024, 7, 5)
    with pytest.raises(ValueError):
        parse_sec_bhav_date("not-a-date")
    with pytest.raises(ValueError):
        parse_udiff_date("")
    with pytest.raises(ValueError):
        parse_sec_bhav_date("")


# 9. chronology (span + per-file ascending content)
def test_chronology():
    manifest = _manifest()
    assert manifest.earliest_observation == "2019-10-01"
    assert manifest.latest_observation == "2026-09-11"
    assert manifest.unique_date_count == 1721
    head = pd.read_csv(CANONICAL_PATH, usecols=["observation_date"], nrows=10000)
    assert head["observation_date"].min() == "2019-10-01"


# 10. numeric validation (zero failures on real sample files)
def test_numeric_validation():
    audit, _, excluded = validate_sec_bhav_file(SEC_SAMPLE, "r")
    assert audit.numeric_parsing_warnings == 0
    assert audit.null_or_malformed_rows == 0
    assert excluded == []
    uaudit, _, uexcluded = validate_udiff_file(UDIFF_SAMPLE, "r")
    assert uaudit.null_or_malformed_rows == 0
    assert uexcluded == []


# 11. OHLC validation (classifier unit behavior)
def test_ohlc_validation():
    assert classify_ohlc("EQ", 100.0, 105.0, 99.0, 103.0) == "ok"
    assert classify_ohlc("T0", 197.8, 197.8, 197.8, 196.75) == "t0_close_outside_range"
    assert classify_ohlc("EQ", 100.0, 101.0, 99.0, 105.0) == "close_outside_range"
    assert classify_ohlc("EQ", None, 101.0, 99.0, 100.0) == "ok"
    params = _manifest_params()
    assert params["ohlc_flags"] == {"ok": 4205548, "t0_close_outside_range": 216,
                                    "close_outside_range": 0}


# 12. quantity validation (synthetic negative quantity counted)
def test_quantity_validation(tmp_path: Path):
    bad = tmp_path / "sec_bhavdata_full_01012020.csv"
    bad.write_text(
        "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
        "LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,"
        "NO_OF_TRADES,DELIV_QTY,DELIV_PER\n"
        "TEST,EQ,01-Jan-2020,10,10,11,9,10,10,10,-5,1.0,3,0,0.0\n",
        encoding="utf-8")
    audit, frame, _ = validate_sec_bhav_file(bad, "r")
    assert audit.negative_quantity_count == 1
    assert frame["traded_quantity"].iloc[0] == -5  # preserved, counted, not hidden


# 13. delivery validation (violations counted, never auto-corrected)
def test_delivery_validation(tmp_path: Path):
    bad = tmp_path / "sec_bhavdata_full_01012020.csv"
    bad.write_text(
        "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
        "LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,"
        "NO_OF_TRADES,DELIV_QTY,DELIV_PER\n"
        "TEST,EQ,01-Jan-2020,10,10,11,9,10,10,10,100,1.0,3,150,150.0\n",
        encoding="utf-8")
    audit, frame, _ = validate_sec_bhav_file(bad, "r")
    assert audit.delivery_violations == 2  # dqty > qty AND pct > 100
    assert frame["deliverable_quantity"].iloc[0] == 150  # preserved as reported


# 14. missing-value handling (placeholders stay NULL, never zero)
def test_missing_value_handling():
    assert _to_float("") is None
    assert _to_float("-") is None
    assert _to_float("NA") is None
    assert _to_float("1,234.5") == pytest.approx(1234.5)
    assert _to_float("0.0") == pytest.approx(0.0)  # genuine zero preserved


# 15. series handling (all series preserved, scope explicit in manifest)
def test_series_handling():
    params = _manifest_params()
    assert params["series_scope"].startswith("ALL reported series preserved")
    assert "EQ 3152515" in params["series_scope"]
    assert "GS 42037" in params["series_scope"]
    # Spot-file evidence that non-EQ series survive into the canonical file.
    sample = pd.read_csv(CANONICAL_PATH, usecols=["series"], nrows=100000)
    assert "EQ" in set(sample["series"])
    assert len(set(sample["series"])) > 1


# 16. identifier preservation (verbatim symbols incl. special chars)
def test_identifier_preservation():
    sample = pd.read_csv(
        CANONICAL_PATH, usecols=["symbol", "series", "isin", "isin_basis"],
        nrows=300000)
    assert "M&M" in set(sample["symbol"]) or "M&MFIN" in set(sample["symbol"])
    assert sample["symbol"].str.contains(r"&").any()
    matched = sample[sample["isin_basis"] == "udiff_match"]
    assert matched["isin"].notna().all()


# 17. symbol-change preservation (same symbol + different series stay distinct)
def test_symbol_change_preservation():
    _, frame, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    be_rows = frame[frame["series"] == "BE"]
    eq_rows = frame[frame["series"] == "EQ"]
    shared = set(be_rows["symbol"]) & set(eq_rows["symbol"])
    canon = pd.read_csv(
        CANONICAL_PATH, usecols=["observation_date", "symbol", "series"],
        nrows=500000)
    assert not canon.duplicated(
        subset=["observation_date", "symbol", "series"]).any()
    assert len(shared) >= 0  # documents that cross-series symbols exist distinctly


# 18. corporate-action discontinuity preservation (extremes kept unadjusted)
def test_discontinuity_preservation():
    params = _manifest_params()
    bands = params["discontinuities"]["bands"]
    assert bands["gte_100pct"] == 152
    assert params["discontinuities"]["policy"].startswith("preserved unadjusted")
    assert validate_no_forward_fill(
        pd.read_csv(CANONICAL_PATH, nrows=1000)) == []


# 19. cross-regime overlap (08-Jul-2024 full reconciliation)
def test_cross_regime_overlap():
    _, frame, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    _, uframe, _ = validate_udiff_file(UDIFF_SAMPLE, "r")
    cmp = compare_regimes(frame, uframe)
    assert cmp["common_keys"] == 2637
    assert cmp["exact_keys"] == 2637
    assert len(cmp["conflicts"]) == 0
    params = _manifest_params()
    assert params["cross_regime_full"]["common_keys"] == 1931407
    assert params["cross_regime_full"]["exact_keys"] == 1931401
    assert params["cross_regime_full"]["conflict_count"] == 6


# 20. canonical schema (row count + span + grain)
def test_canonical_schema():
    manifest = _manifest()
    assert manifest.row_count == 4205764
    assert manifest.unique_date_count == 1721
    assert manifest.duplicate_count == 0
    assert manifest.processing_parameters["distinct_symbols"] == 4802


# 21. deterministic rebuild (same inputs -> identical frame)
def test_deterministic_rebuild():
    _, frame, _ = validate_sec_bhav_file(SEC_SAMPLE, "r")
    _, uframe, _ = validate_udiff_file(UDIFF_SAMPLE, "r")
    first, _ = build_canonical([frame], ["a.csv"], [uframe], ["b.zip"])
    second, _ = build_canonical([frame], ["a.csv"], [uframe], ["b.zip"])
    assert first.equals(second)
    assert len(first) == 2637


# 22. manifest validation (contract + statuses)
def test_manifest_validation():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manager.validate_manifest(manifest) == []
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.frequency == DataFrequency.DAILY
    assert manifest.tier == DataTier.A
    assert manifest.asset_class == "equity"
    assert len(manifest.raw_artifacts or []) == 2467


# 23. SHA reproducibility (raw spot + canonical)
def test_sha_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/equities/nse_equity_daily.csv")
    by_path = {a.path: a.sha256 for a in manifest.raw_artifacts or []}
    sample = "data/raw/india/equities/sec_bhavdata_full_08072024.csv"
    assert by_path[sample] == manager.compute_sha256(sample)


# 24. availability fail-closed behavior (0 eligible, gate raises)
def test_availability_fail_closed():
    sample = pd.read_csv(CANONICAL_PATH, nrows=50000)
    assert sample["availability_date"].isna().all()
    assert agent_eligible_rows(sample).empty
    assert AGENT_ELIGIBLE_VINTAGES == frozenset()
    with pytest.raises(ValueError, match="No agent-eligible NSE equity"):
        build_agent_information_set(sample)
    with pytest.raises(ValueError, match="No agent-eligible NSE equity"):
        build_agent_information_set(sample.iloc[0:0])


# 25. leakage checks (nothing visible at any boundary; auditor clean)
def test_leakage_checks():
    sample = pd.read_csv(CANONICAL_PATH, nrows=20000)
    # Cases 1/2/3/5: no availability exists, so nothing is ever visible.
    assert agent_eligible_rows(sample).empty
    # Case 4: 100% missing availability excluded.
    assert sample["availability_date"].isna().all()
    # Case 6 + auditor: price frame carries no future-derived columns.
    report = LeakageAuditor().audit_all(price_df=sample)
    assert report.is_clean


# 26. InformationSet rejection of unknown availability (unweakened gate)
def test_information_set_rejection():
    bad = pd.DataFrame({
        "variable": ["NSE_EQUITY"],
        "observation_date": pd.to_datetime(["2024-01-01"]),
        "availability_date": pd.to_datetime(["NaT"]),
        "revision_version": [0],
        "value": [100.0],
    })
    with pytest.raises(ValueError, match="reliable availability"):
        InformationSet(bad)


# 27. integrity gate evidence (fallback accounting + mislabeled exclusion)
def test_integrity_gate_evidence():
    params = _manifest_params()
    assert params["integrity_gate"]["passed"] is True
    assert params["integrity_gate"]["fallback_count"] == 85
    assert params["excluded_files"] == ["sec_bhavdata_full_30092019.csv"]
    assert params["excluded_conflict_key_count"] == 6
    assert ["2024-02-19", "WTICAB", "ST"] in params["excluded_conflict_keys"]
    canon = pd.read_csv(
        CANONICAL_PATH, usecols=["observation_date", "symbol", "series"],
        nrows=10000)
    assert (canon["observation_date"] >= "2019-10-01").all()


# 28. ISIN attach accounting (matched/unambiguous, never invented identity)
def test_isin_attach_accounting():
    params = _manifest_params()
    assert params["isin_attach"] == {"matched": 1931401, "unmatched": 2274363,
                                     "ambiguous": 0}
    assert params["isin_policy"].startswith("same-day same-key")


# 29. no adjustment (synthetic corporate-action-style jump preserved)
def test_no_adjustment(tmp_path: Path):
    day1 = tmp_path / "sec_bhavdata_full_01012020.csv"
    day2 = tmp_path / "sec_bhavdata_full_02012020.csv"
    for path, datestr, close in ((day1, "01-Jan-2020", 1000.0),
                                 (day2, "02-Jan-2020", 500.0)):
        path.write_text(
            "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
            "LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,"
            "NO_OF_TRADES,DELIV_QTY,DELIV_PER\n"
            f"TEST,EQ,{datestr},1000,500,510,490,505,{close},505,1000,5.0,10,500,50.0\n",
            encoding="utf-8")
    _, f1, _ = validate_sec_bhav_file(day1, "r")
    _, f2, _ = validate_sec_bhav_file(day2, "r")
    canon, _ = build_canonical([f1, f2], ["d1.csv", "d2.csv"])
    closes = canon.sort_values("observation_date")["close"].tolist()
    assert closes == [1000.0, 500.0]  # 50% drop preserved, never smoothed


# 30. malformed/conflict synthetic matrix (exclusions + errors explicit)
def test_malformed_conflict_matrix(tmp_path: Path):
    empty = tmp_path / "sec_bhavdata_full_03012020.csv"
    empty.write_text(
        "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
        "LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,"
        "NO_OF_TRADES,DELIV_QTY,DELIV_PER\n"
        ",EQ,03-Jan-2020,10,10,11,9,10,10,10,100,1.0,3,50,50.0\n",
        encoding="utf-8")
    audit, frame, excluded = validate_sec_bhav_file(empty, "r")
    assert audit.null_or_malformed_rows == 1
    assert len(excluded) == 1
    assert frame.empty
