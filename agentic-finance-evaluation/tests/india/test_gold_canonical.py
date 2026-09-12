"""MCX Gold futures individual-contract acquisition/validation tests.

Covers the official MCX Bhav Copy FUTCOM GOLD per-expiry CSVs. Raw files
are immutable evidence and are never modified by these tests. No
continuous series is constructed anywhere in this module's scope.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.gold_canonicalize import (
    audit_all_files,
    build_canonical,
    contract_symbol_for,
    detect_overlaps,
    discover_gold_raw_files,
    header_matches_gold_schema,
    parse_expiry,
    parse_trade_date,
    validate_gold_file,
)
from src.india.leakage_audit import LeakageAuditor
from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    EligibilityStatus,
    ValidationStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "gold"
CANONICAL_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "india"
    / "instruments"
    / "mcx_gold_futures_individual_contracts.csv"
)
MANIFEST_ID = "mcx_gold_futures_individual_contracts"

BYTE_DUPE_PAIRS = [
    [
        "BhavCopyCommodiyWise_01012003 - 2026-09-12T171249.888.csv",
        "BhavCopyCommodiyWise_01012003 - 2026-09-12T171255.138.csv",
    ],
    [
        "BhavCopyCommodiyWise_01012003 - 2026-09-12T171341.987.csv",
        "BhavCopyCommodiyWise_01012024.csv",
    ],
]


def _write_gold_file(path: Path, rows: list[str]) -> None:
    path.write_text(
        "Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,"
        "Open,High,Low,Close,Previous Close,Volume(Lots),Volume(In 000's),"
        "Value(Lacs),Open Interest(Lots)\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def _row(trade: str, expiry: str, o: str, h: str, l: str, c: str,
         vol: str = "10", val: str = "100.0", oi: str = "5") -> str:
    return (
        f'"{trade}","FUTCOM","GOLD","{expiry}","-","0",'
        f'"{o}","{h}","{l}","{c}","{c}","{vol}","{vol}.000 GRMS ","{val}","{oi}"'
    )


# 1. raw discovery (143 CSVs, no sidecars in dataset)
def test_raw_files_discovered():
    files = discover_gold_raw_files(RAW_DIR)
    assert len(files) == 143
    assert files == sorted(files)
    assert not list(RAW_DIR.glob("__MACOSX*"))


# 2. exact MCX source/instrument targeting (FUTCOM GOLD only)
def test_instrument_targeting():
    for path in discover_gold_raw_files(RAW_DIR):
        audit, _, _ = validate_gold_file(path, path.name)
        assert audit.header_valid is True
        assert audit.instruments_observed == ["FUTCOM"]
        assert audit.symbols_observed == ["GOLD"]
    assert header_matches_gold_schema(
        ["Date", "Instrument Name", "Symbol", "Expiry Date", "Option Type",
         "Strike Price", "Open", "High", "Low", "Close", "Previous Close",
         "Volume(Lots)", "Volume(In 000's)", "Value(Lacs)", "Open Interest(Lots)"]
    )


# 3. contract identifier + expiry preservation
def test_contract_identifier_preservation():
    assert contract_symbol_for(date(2004, 2, 13)) == "GOLDFEB2004"
    assert parse_expiry("05FEB2004") == date(2004, 2, 5)
    with pytest.raises(ValueError):
        parse_expiry("NOT-AN-EXPIRY")
    df = pd.read_csv(CANONICAL_PATH)
    assert df["contract_symbol"].nunique() == 141
    assert df["expiry_date"].min() == "2004-02-13"
    assert df["expiry_date"].max() == "2027-08-05"


# 4. trade-date parsing
def test_trade_date_parsing():
    assert parse_trade_date("14 Apr 2004") == date(2004, 4, 14)
    with pytest.raises(ValueError):
        parse_trade_date("NOT-A-DATE")
    with pytest.raises(ValueError):
        parse_trade_date("")


# 5. schema (15 MCX columns, uniform header)
def test_schema():
    for path in discover_gold_raw_files(RAW_DIR):
        audit, _, _ = validate_gold_file(path, path.name)
        assert len(audit.header) == 15
        assert audit.has_bom is False


# 6. numeric validity (zero failures on real artifacts)
def test_numeric_validity():
    total_failures = 0
    total_nonpos = 0
    total_malformed = 0
    for path in discover_gold_raw_files(RAW_DIR):
        audit, _, _ = validate_gold_file(path, path.name)
        total_failures += audit.numeric_parsing_failures
        total_nonpos += audit.nonpositive_count
        total_malformed += audit.null_or_malformed_rows
    assert total_failures == 0
    assert total_nonpos == 0
    assert total_malformed == 0


# 7. OHLC validation with explicit anomaly classification (preserved, not deleted)
def test_ohlc_classification_preserved():
    df = pd.read_csv(CANONICAL_PATH)
    flags = df["ohlc_flag"].value_counts().to_dict()
    assert flags.get("expiry_close_outside_range", 0) == 49
    assert flags.get("close_outside_range", 0) == 5
    assert flags.get("no_trade_ohlc_null", 0) == 9933
    assert flags.get("ok", 0) == 19659
    expiring = df[df["trade_date"] == df["expiry_date"]]
    assert set(expiring["ohlc_flag"]) <= {"ok", "expiry_close_outside_range"}


# 8. duplicate handling (no within-file natural-key dupes)
def test_duplicate_handling():
    for path in discover_gold_raw_files(RAW_DIR):
        audit, _, _ = validate_gold_file(path, path.name)
        assert audit.duplicate_keys_within_file == 0


# 9. multi-contract same-date preservation (never collapsed)
def test_multi_contract_same_date_preserved():
    df = pd.read_csv(CANONICAL_PATH)
    per_date = df.groupby("trade_date")["contract_symbol"].nunique()
    assert int((per_date > 1).sum()) == 6309
    assert not df.duplicated(subset=["trade_date", "expiry_date"]).any()


# 10. cross-file duplicate reconciliation (byte-dupe pairs share provenance)
def test_cross_file_duplicate_reconciliation():
    for first, second in BYTE_DUPE_PAIRS:
        first_bytes = (RAW_DIR / first).read_bytes()
        second_bytes = (RAW_DIR / second).read_bytes()
        assert hashlib.sha256(first_bytes).hexdigest() == hashlib.sha256(second_bytes).hexdigest()
    files = discover_gold_raw_files(RAW_DIR)
    frames = [validate_gold_file(p, p.name)[1] for p in files]
    overlaps = detect_overlaps(frames, [p.name for p in files])
    assert len(overlaps) == 270
    assert all(item.identical for item in overlaps)
    df = pd.read_csv(CANONICAL_PATH)
    assert len(df) == 29916 - 270


# 11. conflict detection (synthetic conflicting overlap halts)
def test_conflict_detection(tmp_path: Path):
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_gold_file(first, [_row("01 Jun 2020", "05JUN2020", "46000", "46100", "45900", "46050")])
    _write_gold_file(second, [_row("01 Jun 2020", "05JUN2020", "46000", "46100", "45900", "99999")])
    frames = [
        validate_gold_file(first, first.name)[1],
        validate_gold_file(second, second.name)[1],
    ]
    overlaps = detect_overlaps(frames, [first.name, second.name])
    assert len(overlaps) == 1 and overlaps[0].identical is False
    with pytest.raises(ValueError, match="Conflicting overlapping"):
        build_canonical(frames, [first.name, second.name], overlaps)


# 12. chronology (per-contract ascending in canonical)
def test_chronology():
    df = pd.read_csv(CANONICAL_PATH)
    for _, group in df.groupby("contract_symbol"):
        dates = pd.to_datetime(group["trade_date"])
        assert dates.is_monotonic_increasing
        assert not dates.duplicated().any()
    assert df["trade_date"].min() == "2003-11-10"
    assert df["trade_date"].max() == "2026-09-11"


# 13. missing settlement handling (null, never mapped from Close)
def test_missing_settlement_handling():
    df = pd.read_csv(CANONICAL_PATH)
    assert df["settlement_price"].isna().all()
    assert not (df["settlement_price"] == df["close"]).any()


# 14. source-field/unit preservation (no silent conversion)
def test_source_field_unit_preservation():
    df = pd.read_csv(CANONICAL_PATH)
    assert (df["source"] == "MCX").all()
    assert (df["volume"] >= 0).all()
    assert (df["open_interest"] >= 0).all()
    assert (df["turnover"] >= 0).all()
    assert "ohlc_flag" in df.columns


# 15. leakage (gold branch clean, no roll constructed, causal boundary)
def test_leakage():
    df = pd.read_csv(CANONICAL_PATH)
    assert not any(
        any(token in str(col).lower() for token in ("future", "forward", "next_", "lead_"))
        for col in df.columns
    )
    assert "roll_applied" not in df.columns
    assert "continuous" not in " ".join(str(col) for col in df.columns).lower()
    report = LeakageAuditor().audit_all(price_df=df, gold_contracts_df=df)
    assert report.is_clean
    assert any(v.violation_type == "GOLD_ROLL_NOT_CONSTRUCTED" for v in report.mitigated)
    cutoff = pd.Timestamp("2020-01-01")
    visible = df[pd.to_datetime(df["trade_date"]) <= cutoff]
    hidden = df[pd.to_datetime(df["trade_date"]) > cutoff]
    assert len(visible) > 0 and len(hidden) > 0
    assert pd.to_datetime(visible["trade_date"]).max() <= cutoff


# 16. no continuous-series fabrication
def test_no_continuous_series():
    df = pd.read_csv(CANONICAL_PATH)
    assert "contract_symbol" in df.columns
    assert df["contract_symbol"].nunique() == 141
    assert "expiry_date" in df.columns


# 17. blocked eligibility
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.eligibility_status != EligibilityStatus.EXPERIMENT_ELIGIBLE


# 18. manifest bookkeeping (29916 - 270 - 0 = 29646)
def test_manifest_bookkeeping():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    params = manifest.processing_parameters
    assert params["total_raw_rows"] == 29916
    assert params["unique_contracts"] == 141
    assert params["identical_overlaps_deduped"] == 270
    assert params["conflicting_overlaps"] == 0
    assert params["excluded_invalid_rows"] == []
    assert params["roll"] == "NOT constructed; methodology deferred to a separate milestone"
    assert manifest.row_count == 29646
    assert len(manifest.raw_paths or []) == 143
    assert len(manifest.raw_artifacts or []) == 143


# 19. SHA reproducibility (raw + canonical)
def test_sha_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv"
    )
    assert manifest.raw_artifacts
    for artifact in manifest.raw_artifacts:
        assert artifact.sha256 == manager.compute_sha256(artifact.path)
