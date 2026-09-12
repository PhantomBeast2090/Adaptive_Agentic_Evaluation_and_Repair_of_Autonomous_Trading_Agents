"""MoSPI CPI Combined General index (2012=100) acquisition/validation tests.

Covers All-India CPI Combined General index, base 2012=100, January 2013 to
December 2025. Raw press-release PDFs under data/raw/india/macro/cpi/ are
immutable evidence and are never modified by tests. Full PDF re-parsing is
deliberately avoided in the suite (110 files); parser behaviour is pinned by
fast spot-checks on individual raw files plus synthetic vintage fixtures.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.cpi_canonicalize import (
    AGENT_ELIGIBLE_VINTAGES,
    BACKBONE_FILE,
    CpiReleaseEvidence,
    REVISION_RELEASE_DATE,
    REVISION_RELEASE_FILE,
    agent_eligible_rows,
    build_agent_information_set,
    build_canonical,
    detect_base,
    discover_cpi_raw_files,
    extract_compact_provisional,
    extract_general_combined,
    month_end,
    read_pdf_text,
    validate_no_forward_fill,
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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "macro" / "cpi"
CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "india" / "macro"
    / "mospi_cpi_combined_monthly.csv"
)
MANIFEST_ID = "mospi_cpi_combined_monthly"


def _canonical() -> pd.DataFrame:
    return pd.read_csv(CANONICAL_PATH)


# 1. raw discovery (official MoSPI/PIB artifacts, immutable)
def test_raw_artifacts_discovered():
    files = discover_cpi_raw_files(RAW_DIR)
    assert len(files) == 111
    assert all(p.suffix.lower() in (".pdf", ".html") for p in files)
    assert (RAW_DIR / BACKBONE_FILE).exists()
    assert (RAW_DIR / REVISION_RELEASE_FILE).exists()


# 2. exact series targeting (2012-base homogeneous window only)
def test_series_targeting_and_base_detection():
    assert detect_base("CONSUMER PRICE INDEX NUMBERS ON BASE 2012=100") == "2012"
    assert detect_base("CONSUMER PRICE INDEX NUMBERS ON BASE 2010=100") == "2010"
    assert detect_base("no base mentioned") is None
    df = _canonical()
    assert (df["source"] == "MOSPI").all()
    assert "inflation_yoy_pct" not in df.columns  # index-only canonical


# 3. schema (index-only, source-supported fields)
def test_schema():
    df = _canonical()
    assert list(df.columns) == [
        "observation_period", "observation_date", "availability_date",
        "cpi_index", "vintage_status", "revision_version",
        "availability_basis", "source", "source_files",
    ]
    assert df["cpi_index"].notna().all()
    assert (df["cpi_index"] > 0).all()


# 4. homogeneous window (Jan-2013..Dec-2025, 156 consecutive months)
def test_homogeneous_window():
    df = _canonical()
    assert df["observation_period"].nunique() == 156
    assert df["observation_period"].min() == "2013-01"
    assert df["observation_period"].max() == "2025-12"
    periods = pd.period_range("2013-01", "2025-12", freq="M").strftime("%Y-%m")
    assert sorted(df["observation_period"].unique()) == list(periods)
    # Jun-2019 is present in the MoSPI series (an RBI-workbook omission
    # elsewhere must never be replicated here).
    assert "2019-06" in set(df["observation_period"])


# 5. observation-period semantics (month-end technical dates)
def test_observation_period_semantics():
    assert month_end(2025, 2) == date(2025, 2, 28)
    assert month_end(2024, 2) == date(2024, 2, 29)
    df = _canonical()
    dates = pd.to_datetime(df["observation_date"])
    assert ((dates.dt.is_month_end)).all()
    assert (
        df["observation_period"]
        == dates.dt.strftime("%Y-%m")
    ).all()


# 6. provisional -> final vintage structure (genuine revision preserved)
def test_provisional_final_vintages():
    df = _canonical()
    jan25 = df[df["observation_period"] == "2025-01"].sort_values(
        "revision_version")
    assert len(jan25) == 2
    assert jan25.iloc[0]["vintage_status"] == "provisional"
    assert jan25.iloc[0]["cpi_index"] == pytest.approx(193.5)
    assert jan25.iloc[1]["vintage_status"] == "final"
    assert jan25.iloc[1]["cpi_index"] == pytest.approx(193.4)
    assert set(df["vintage_status"]) <= {
        "provisional", "final", "imputed",
        "revision_back_series", "final_series_only",
    }


# 6b. finals kept per-evidence (month need not have its own release)
def test_final_without_own_release():
    df = _canonical()
    feb20 = df[(df["observation_period"] == "2020-02")
               & (df["vintage_status"] == "final")]
    assert len(feb20) == 1
    assert feb20.iloc[0]["cpi_index"] == pytest.approx(149.1)
    assert feb20.iloc[0]["availability_date"] == "2020-04-13"
    dec14 = df[(df["observation_period"] == "2014-12")
               & (df["vintage_status"] == "final")]
    assert len(dec14) == 1
    assert dec14.iloc[0]["cpi_index"] == pytest.approx(119.4)
    assert dec14.iloc[0]["availability_date"] == "2015-02-12"


# 7. lockdown imputed vintages (Apr/May-2020 published 2020-07-13)
def test_imputed_lockdown_vintages():
    df = _canonical()
    for period, value in (("2020-04", 151.4), ("2020-05", 150.9)):
        rows = df[df["observation_period"] == period]
        assert len(rows) == 1
        assert rows.iloc[0]["vintage_status"] == "imputed"
        assert rows.iloc[0]["cpi_index"] == pytest.approx(value)
        assert rows.iloc[0]["availability_date"] == "2020-07-13"


# 8. revision back-series (2013-2014 availability anchored to revision)
def test_revision_back_series():
    df = _canonical()
    back = df[df["vintage_status"] == "revision_back_series"]
    assert len(back) == 23
    assert back["observation_period"].min() == "2013-01"
    assert back["observation_period"].max() == "2014-11"
    assert (back["availability_date"] == "2015-02-12").all()
    assert back["availability_basis"].str.contains(
        "revision_back_series").all()
    assert REVISION_RELEASE_DATE == date(2015, 2, 12)


# 9. compact COVID-era table regression (June-2020 provisional parsed)
def test_compact_table_regression():
    text = read_pdf_text(RAW_DIR / "CPI Press Release June 2020.pdf")
    import re as _re
    normalized = _re.sub(r"\s+", " ", text)
    assert extract_general_combined(normalized) is None
    compact = extract_compact_provisional(normalized)
    assert compact is not None
    assert compact[2] == pytest.approx(151.6)
    df = _canonical()
    jun20 = df[(df["observation_period"] == "2020-06")
               & (df["vintage_status"] == "provisional")]
    assert len(jun20) == 1
    assert jun20.iloc[0]["cpi_index"] == pytest.approx(151.6)


# 10. duplicate re-upload merge (Sep-2022 single logical vintage)
def test_duplicate_reupload_merge():
    df = _canonical()
    sep22 = df[(df["observation_period"] == "2022-09")
               & (df["vintage_status"] == "provisional")]
    assert len(sep22) == 1
    assert sep22.iloc[0]["cpi_index"] == pytest.approx(175.3)
    sources = sep22.iloc[0]["source_files"]
    assert "CPI_PR_12oct22.pdf" in sources
    assert "CPI_PR_September_2022.pdf" in sources


# 11. manifest bookkeeping (82 + 82 + 2 + 23 + 20 = 209)
def test_manifest_bookkeeping():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.row_count == 209
    assert manifest.unique_date_count == 156  # distinct YYYY-MM periods
    assert manifest.duplicate_count == 0
    params = manifest.processing_parameters
    assert params["canonical_rows"] == 209
    assert params["conflicting_overlaps"] == 0
    assert params["vintage_counts"] == {
        "final": 82, "final_series_only": 20, "imputed": 2,
        "provisional": 82, "revision_back_series": 23,
    }
    df = _canonical()
    assert len(df) == 209


# 12. SHA reproducibility (processed + raw backbone)
def test_sha_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/macro/mospi_cpi_combined_monthly.csv"
    )
    assert manifest.raw_artifacts is not None
    assert len(manifest.raw_artifacts) == 111
    backbone = next(a for a in manifest.raw_artifacts
                    if a.path.endswith(BACKBONE_FILE))
    assert backbone.sha256 == manager.compute_sha256(backbone.path)


# 13. blocked eligibility (acquired/passed/blocked, never eligible)
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.frequency == DataFrequency.MONTHLY


# 14. no fabrication (nulls stay null; values positive; months continuous)
def test_no_fabrication():
    df = _canonical()
    assert validate_no_forward_fill(df) == []
    unverified = df[df["availability_basis"] == "unverified"]
    assert len(unverified) == 20
    assert unverified["availability_date"].isna().all()
    assert (df["cpi_index"] > 0).all()


# 15. LEAKAGE CASE 1: unreleased observation hidden
def test_leakage_unreleased_hidden():
    info = build_agent_information_set(_canonical())
    # November 2025 released 2025-12-12: invisible the day before.
    visible = info.information_available_at("2025-12-11")
    assert "2025-11-30" not in set(
        pd.to_datetime(visible["observation_date"]).dt.strftime("%Y-%m-%d"))


# 16. LEAKAGE CASE 2: released observation visible
def test_leakage_released_visible():
    info = build_agent_information_set(_canonical())
    visible = info.information_available_at("2025-12-12")
    nov = visible[visible["observation_date"] == "2025-11-30"]
    assert len(nov) == 1
    assert float(nov.iloc[0]["value"]) == pytest.approx(197.9)


# 17. LEAKAGE CASE 3: later revision cannot back-leak
def test_leakage_revision_no_backleak():
    info = build_agent_information_set(_canonical())
    # Jan-2025 final (193.4) available 2025-03-12 must not displace the
    # provisional (193.5) visible in February 2025.
    feb = info.information_available_at("2025-02-20")
    jan_feb = feb[feb["observation_date"] == "2025-01-31"]
    assert float(jan_feb.iloc[0]["value"]) == pytest.approx(193.5)
    mar = info.information_available_at("2025-03-13")
    jan_mar = mar[mar["observation_date"] == "2025-01-31"]
    assert float(jan_mar.iloc[0]["value"]) == pytest.approx(193.4)


# 18. LEAKAGE CASE 4: missing release timing excluded from agent set
def test_leakage_missing_release_excluded():
    df = _canonical()
    eligible = agent_eligible_rows(df)
    assert set(eligible["vintage_status"]) <= AGENT_ELIGIBLE_VINTAGES
    assert "final_series_only" not in set(eligible["vintage_status"])
    merged = eligible.merge(
        df[df["vintage_status"] == "final_series_only"][
            ["observation_period"]].drop_duplicates(),
        on="observation_period", how="inner")
    assert merged.empty
    assert len(eligible) == 189


# 19. LEAKAGE CASE 5: future observation hidden
def test_leakage_future_hidden():
    info = build_agent_information_set(_canonical())
    visible = info.information_available_at("2020-01-15")
    assert (pd.to_datetime(visible["observation_date"])
            <= pd.Timestamp("2020-01-15")).all()
    assert "2025-12-31" not in set(
        pd.to_datetime(visible["observation_date"]).dt.strftime("%Y-%m-%d"))


# 20. LEAKAGE CASE 6: environment rich, agent clean
def test_leakage_environment_rich_agent_clean():
    df = _canonical()
    assert len(df) == 209  # environment retains everything incl. nulls
    assert len(agent_eligible_rows(df)) == 189  # eligible vintages
    info = build_agent_information_set(df)
    visible = info.information_available_at("2026-08-01")
    # Latest eligible vintage per period: 136 verified months.
    assert len(visible) == 136
    assert len(visible) == df[df["availability_date"].notna()][
        "observation_period"].nunique()


# 21. agent gate fails closed
def test_agent_gate_fails_closed():
    with pytest.raises(ValueError, match="No agent-eligible CPI"):
        build_agent_information_set(_canonical().iloc[0:0])
    empty = pd.DataFrame(columns=list(_canonical().columns))
    with pytest.raises(ValueError, match="No agent-eligible CPI"):
        build_agent_information_set(empty)


# 22. conflict path blocks on backbone deviation (synthetic, no PDFs)
def test_conflict_blocks_backbone_deviation():
    evidence = [CpiReleaseEvidence(
        filename="synthetic.pdf", ref_year=2024, ref_month=6,
        release_date=date(2024, 7, 12), release_basis="mospi_press_release",
        base="2012", comb_prev_final=999.0, comb_prov=190.5)]
    frame, _, conflicts = build_canonical(
        evidence, {(2024, 5): 190.0, (2024, 6): 190.5}, BACKBONE_FILE)
    assert any(c.observation_period == "2024-05" for c in conflicts)
    assert len(conflicts) == 1


# 23. RBI cross-check corroboration (frozen workbook, tight tolerance)
def test_rbi_crosscheck_corroboration():
    import openpyxl
    raw = (PROJECT_ROOT / "data" / "raw" / "india" / "fixed_income"
           / "50 Macroeconomic Indicators.xlsx")
    workbook = openpyxl.load_workbook(raw, read_only=True, data_only=True)
    sheet = workbook["Monthly"]
    month_num = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,
                 "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10,
                 "Nov": 11, "Dec": 12}
    df = _canonical()
    finals = {}
    for period, group in df.groupby("observation_period"):
        ordered = group.sort_values("revision_version")
        finals[period] = float(ordered.iloc[-1]["cpi_index"])
    diffs = []
    for row in list(sheet.iter_rows(values_only=True))[4:]:
        period, value = row[1], row[2]
        if period is None or value is None or str(value).strip() == "-":
            continue
        mon, year = str(period).split("-")
        key = f"{int(year):04d}-{month_num[mon]:02d}"
        if key in finals:
            diffs.append(abs(float(value) - finals[key]))
    assert len(diffs) == 98
    assert max(diffs) <= 0.11


# 24. leakage auditor price-frame clean
def test_leakage_auditor_clean():
    df = _canonical()
    report = LeakageAuditor().audit_all(price_df=df)
    assert report.is_clean
