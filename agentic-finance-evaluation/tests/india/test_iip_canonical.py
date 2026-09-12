"""MoSPI IIP General Index (2011-12=100) acquisition/validation tests.

Covers All-India IIP General Index level, base 2011-12=100, April 2012 to
March 2026. Raw press-release PDFs under data/raw/india/macro/iip/ are
immutable evidence and are never modified by tests. Full PDF re-parsing is
deliberately avoided in the suite (130+ files); parser behaviour is pinned
by fast spot-checks on individual raw files plus synthetic fixtures.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.iip_canonicalize import (
    AGENT_ELIGIBLE_VINTAGES,
    BACKSERIES_FILE,
    BACKSERIES_RELEASE_DATE,
    IipReleaseEvidence,
    agent_eligible_rows,
    build_agent_information_set,
    build_canonical,
    detect_base,
    discover_iip_raw_files,
    month_end,
    parse_backseries,
    parse_release_pdf,
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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "macro" / "iip"
CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "india" / "macro"
    / "mospi_iip_general_monthly.csv"
)
MANIFEST_ID = "mospi_iip_general_monthly"


def _canonical() -> pd.DataFrame:
    return pd.read_csv(CANONICAL_PATH)


# 1. raw discovery (official MoSPI/PIB artifacts, immutable)
def test_raw_artifacts_discovered():
    files = discover_iip_raw_files(RAW_DIR)
    assert len(files) == 132
    assert all(p.suffix.lower() in (".pdf", ".html") for p in files)
    assert (RAW_DIR / BACKSERIES_FILE).exists()


# 2. exact series targeting (2011-12 base only; others excluded)
def test_series_targeting_and_base_detection():
    assert detect_base("INDEX (BASE 2011-12=100)") == "2011-12"
    assert detect_base("INDEX (Base :2011-12=100)") == "2011-12"
    assert detect_base("INDEX (BASE 2004-05=100)") == "2004-05"
    assert detect_base("INDEX (Base 2022-23=100)") == "2022-23"
    assert detect_base("no base mentioned") is None
    df = _canonical()
    assert (df["source"] == "MOSPI").all()
    assert "growth_yoy_pct" not in df.columns  # index-only canonical


# 3. schema (index-only, source-supported fields)
def test_schema():
    df = _canonical()
    assert list(df.columns) == [
        "observation_period", "observation_date", "availability_date",
        "iip_index", "vintage_status", "revision_version",
        "availability_basis", "source", "source_files",
    ]
    assert df["iip_index"].notna().all()
    assert (df["iip_index"] > 0).all()


# 4. homogeneous window (Apr-2012..Mar-2026, 168 consecutive months)
def test_homogeneous_window():
    df = _canonical()
    assert df["observation_period"].nunique() == 168
    assert df["observation_period"].min() == "2012-04"
    assert df["observation_period"].max() == "2026-03"
    periods = pd.period_range("2012-04", "2026-03", freq="M").strftime("%Y-%m")
    assert sorted(df["observation_period"].unique()) == list(periods)


# 5. observation-period semantics (month-end technical dates)
def test_observation_period_semantics():
    assert month_end(2020, 2) == date(2020, 2, 29)
    assert month_end(2026, 3) == date(2026, 3, 31)
    df = _canonical()
    dates = pd.to_datetime(df["observation_date"])
    assert (dates.dt.is_month_end).all()
    assert (df["observation_period"] == dates.dt.strftime("%Y-%m")).all()


# 6. quick/first/final vintage timeline (Jul-2023: 142.0 -> 142.5 -> 142.7)
def test_quick_first_final_timeline():
    df = _canonical()
    jul23 = df[df["observation_period"] == "2023-07"].sort_values(
        "revision_version")
    assert len(jul23) == 3
    assert jul23.iloc[0]["vintage_status"] == "quick"
    assert jul23.iloc[0]["iip_index"] == pytest.approx(142.0)
    assert jul23.iloc[0]["availability_date"] == "2023-09-12"
    assert jul23.iloc[1]["vintage_status"] == "first_revision"
    assert jul23.iloc[1]["iip_index"] == pytest.approx(142.5)
    assert jul23.iloc[2]["vintage_status"] == "final"
    assert jul23.iloc[2]["iip_index"] == pytest.approx(142.7)
    assert set(df["vintage_status"]) <= {
        "quick", "first_revision", "final", "back_series", "republished",
    }


# 7. back-series baseline (60 months, available 2017-05-12)
def test_back_series_baseline():
    df = _canonical()
    back = df[df["vintage_status"] == "back_series"]
    assert len(back) == 60
    assert back["observation_period"].min() == "2012-04"
    assert back["observation_period"].max() == "2017-03"
    assert (back["availability_date"] == "2017-05-12").all()
    assert BACKSERIES_RELEASE_DATE == date(2017, 5, 12)
    apr12 = back[back["observation_period"] == "2012-04"]
    assert apr12.iloc[0]["iip_index"] == pytest.approx(99.3)


# 8. COVID lockdown timeline (Apr-2020: 56.3 -> 53.6 -> 54.0, as stated)
def test_covid_lockdown_timeline():
    df = _canonical()
    apr20 = df[df["observation_period"] == "2020-04"].sort_values(
        "revision_version")
    assert len(apr20) == 3
    assert apr20.iloc[0]["vintage_status"] == "quick"
    assert apr20.iloc[0]["iip_index"] == pytest.approx(56.3)
    assert apr20.iloc[0]["availability_date"] == "2020-06-12"
    assert apr20.iloc[1]["vintage_status"] == "first_revision"
    assert apr20.iloc[2]["vintage_status"] == "final"
    assert apr20.iloc[2]["iip_index"] == pytest.approx(54.0)


# 9. revision-model pattern (R1 = M-1, Final = M-3 in classic releases)
def test_revision_model_pattern():
    evidence = parse_release_pdf(RAW_DIR / "IIP_PR_12oct22.pdf")
    assert (evidence.ref_year, evidence.ref_month) == (2022, 8)
    assert evidence.release_date == date(2022, 10, 12)
    assert (2022, 7) in [(y, m) for y, m in
                         evidence.first_revision_months]
    assert (2022, 5) in [(y, m) for y, m in evidence.final_revision_months]


# 10. new-format finals (Mar-2025 release finalizes Dec-2024..Feb-2025)
def test_new_format_finals():
    evidence = parse_release_pdf(RAW_DIR / "IIP_PR_28apr25.pdf")
    assert (evidence.ref_year, evidence.ref_month) == (2025, 3)
    finals = set(evidence.final_revision_months)
    assert (2024, 12) in finals
    assert (2025, 2) in finals
    df = _canonical()
    dec24 = df[(df["observation_period"] == "2024-12")
               & (df["vintage_status"] == "final")]
    assert len(dec24) >= 1


# 11. duplicate re-upload merge (May-2019 triple, identical bytes)
def test_duplicate_reupload_merge():
    import hashlib
    files = ["Press Note May'19.pdf", "Press_Note_May19.pdf", "iipmay19.pdf"]
    hashes = set()
    for name in files:
        path = RAW_DIR / name
        assert path.exists()
        hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
    assert len(hashes) == 1
    df = _canonical()
    may19 = df[(df["observation_period"] == "2019-05")
               & (df["vintage_status"] == "quick")]
    assert len(may19) == 1
    assert may19.iloc[0]["iip_index"] == pytest.approx(133.6)


# 12. named-but-unvalued early revisions preserved without fabrication
def test_unvalued_early_revisions():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    params = manifest.processing_parameters
    assert params["conflicting_overlaps"] == 0
    assert str(params["unvalued_named_revisions"]).startswith("10 ")
    # Months stay covered despite unvalued namings (back-series baseline).
    df = _canonical()
    assert "2017-03" in set(df["observation_period"])
    mar17 = df[df["observation_period"] == "2017-03"]
    assert (mar17["availability_date"].notna()).all()


# 13. manifest bookkeeping (89 + 70 + 81 + 60 + 45 = 345)
def test_manifest_bookkeeping():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.row_count == 345
    assert manifest.unique_date_count == 168
    assert manifest.duplicate_count == 0
    params = manifest.processing_parameters
    assert params["canonical_rows"] == 345
    assert params["conflicting_overlaps"] == 0
    assert params["vintage_counts"] == {
        "back_series": 60, "final": 81, "first_revision": 70,
        "quick": 89, "republished": 45,
    }
    df = _canonical()
    assert len(df) == 345


# 14. SHA reproducibility (processed + raw backbone)
def test_sha_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/macro/mospi_iip_general_monthly.csv"
    )
    assert manifest.raw_artifacts is not None
    assert len(manifest.raw_artifacts) == 132
    backbone = next(a for a in manifest.raw_artifacts
                    if a.path.endswith(BACKSERIES_FILE))
    assert backbone.sha256 == manager.compute_sha256(backbone.path)


# 15. blocked eligibility (acquired/passed/blocked, never eligible)
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.frequency == DataFrequency.MONTHLY


# 16. no fabrication (positive, dated, continuous months)
def test_no_fabrication():
    df = _canonical()
    assert validate_no_forward_fill(df) == []
    assert df["availability_date"].notna().all()
    assert (df["iip_index"] > 0).all()


# 17. LEAKAGE CASE 1: unreleased observation hidden
def test_leakage_unreleased_hidden():
    info = build_agent_information_set(_canonical())
    # August 2023 released 2023-10-12: invisible the day before.
    visible = info.information_available_at("2023-10-11")
    assert "2023-08-31" not in set(
        pd.to_datetime(visible["observation_date"]).dt.strftime("%Y-%m-%d"))


# 18. LEAKAGE CASE 2: released observation visible
def test_leakage_released_visible():
    info = build_agent_information_set(_canonical())
    visible = info.information_available_at("2023-10-12")
    aug = visible[visible["observation_date"] == "2023-08-31"]
    assert len(aug) == 1
    assert float(aug.iloc[0]["value"]) == pytest.approx(145.1)


# 19. LEAKAGE CASE 3: later revision cannot back-leak
def test_leakage_revision_no_backleak():
    info = build_agent_information_set(_canonical())
    # July 2023 final (142.7) available 2023-12-12 must not displace the
    # first revision (142.5) visible in November 2023.
    nov = info.information_available_at("2023-11-15")
    jul_nov = nov[nov["observation_date"] == "2023-07-31"]
    assert float(jul_nov.iloc[0]["value"]) == pytest.approx(142.5)
    dec = info.information_available_at("2023-12-13")
    jul_dec = dec[dec["observation_date"] == "2023-07-31"]
    assert float(jul_dec.iloc[0]["value"]) == pytest.approx(142.7)


# 20. LEAKAGE CASE 4: null availability excluded (synthetic + gate)
def test_leakage_missing_release_excluded():
    df = _canonical()
    eligible = agent_eligible_rows(df)
    assert set(eligible["vintage_status"]) <= AGENT_ELIGIBLE_VINTAGES
    assert len(eligible) == len(df)  # all rows carry verified dates here
    broken = df.copy()
    broken.loc[broken.index[0], "availability_date"] = None
    gated = agent_eligible_rows(broken)
    assert len(gated) == len(df) - 1


# 21. LEAKAGE CASE 5: future observation hidden
def test_leakage_future_hidden():
    info = build_agent_information_set(_canonical())
    visible = info.information_available_at("2020-01-15")
    assert (pd.to_datetime(visible["observation_date"])
            <= pd.Timestamp("2020-01-15")).all()
    assert "2026-03-31" not in set(
        pd.to_datetime(visible["observation_date"]).dt.strftime("%Y-%m-%d"))


# 22. LEAKAGE CASE 6: environment rich, agent clean
def test_leakage_environment_rich_agent_clean():
    df = _canonical()
    assert len(df) == 345
    info = build_agent_information_set(df)
    visible = info.information_available_at("2026-08-01")
    # Latest eligible vintage per period: all 168 verified months.
    assert len(visible) == 168


# 23. agent gate fails closed
def test_agent_gate_fails_closed():
    with pytest.raises(ValueError, match="No agent-eligible IIP"):
        build_agent_information_set(_canonical().iloc[0:0])


# 24. conflict path blocks same-key contradictions (synthetic, no PDFs)
def test_conflict_blocks_contradiction():
    from src.india.iip_canonicalize import _fy_to_year  # noqa: F401
    first = IipReleaseEvidence(
        filename="a.pdf", ref_year=2024, ref_month=6,
        release_date=date(2024, 8, 12), release_basis="mospi_press_release",
        base="2011-12", qe_general=100.0)
    second = IipReleaseEvidence(
        filename="b.pdf", ref_year=2024, ref_month=6,
        release_date=date(2024, 8, 12), release_basis="mospi_press_release",
        base="2011-12", qe_general=999.0)
    frame, _, conflicts, _ = build_canonical(
        [first, second], {}, BACKSERIES_FILE)
    assert any(c.observation_period == "2024-06" for c in conflicts)
    assert "2024-06" not in set(frame["observation_period"])


# 25. RBI corroboration bound (exact pre-break sample + documented break)
def test_rbi_corroboration_bound():
    import openpyxl
    raw = (PROJECT_ROOT / "data" / "raw" / "india" / "fixed_income"
           / "50 Macroeconomic Indicators.xlsx")
    workbook = openpyxl.load_workbook(raw, read_only=True, data_only=True)
    sheet = workbook["Monthly"]
    month_num = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,
                 "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10,
                 "Nov": 11, "Dec": 12}
    rbi = {}
    for row in list(sheet.iter_rows(values_only=True))[4:]:
        period, value = row[1], row[4]
        if period is None or value is None or str(value).strip() == "-":
            continue
        mon, year = str(period).split("-")
        rbi[f"{int(year):04d}-{month_num[mon]:02d}"] = float(value)
    df = _canonical()
    finals = {}
    for period, group in df.groupby("observation_period"):
        ordered = group.sort_values("revision_version")
        finals[period] = float(ordered.iloc[-1]["iip_index"])
    # Exact match through Mar-2023 (pre-break RBI column).
    for period in ["2022-11", "2022-12", "2023-01", "2023-02", "2023-03"]:
        assert abs(rbi[period] - finals[period]) <= 0.011


# 26. leakage auditor price-frame clean
def test_leakage_auditor_clean():
    df = _canonical()
    report = LeakageAuditor().audit_all(price_df=df)
    assert report.is_clean
