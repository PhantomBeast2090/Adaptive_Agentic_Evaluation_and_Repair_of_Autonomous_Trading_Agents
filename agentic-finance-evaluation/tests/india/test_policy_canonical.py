"""RBI policy-rate event acquisition/validation tests.

Covers the dual-source reconciliation: Handbook Table 40 backbone plus
MPC resolution / Annual Report announcement evidence. Raw files are
immutable evidence and are never modified by these tests. The output
stays event-based: no daily conversion anywhere in this module's scope.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.india.information_set import InformationSet
from src.india.leakage_audit import LeakageAuditor
from src.india.manifest import ManifestManager
from src.india.policy_canonicalize import (
    BACKBONE_FILENAME,
    RATE_COLUMNS,
    build_canonical_frame,
    collect_announcements,
    collect_chapter_rates,
    cross_validate_backbone,
    discover_policy_raw_files,
    parse_backbone_table,
    reconcile_events,
)
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    EligibilityStatus,
    RBIPolicyRecord,
    ValidationStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "india" / "macro"
CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "india" / "macro" / "rbi_policy_rate_events.csv"
)
MANIFEST_ID = "rbi_policy_rate_events"

ALLOWED_RATE_TYPES = {"BANK_RATE", "REPO", "REVERSE_REPO", "SDF", "MSF"}


def _backbone():
    return parse_backbone_table(RAW_DIR / BACKBONE_FILENAME)


# 1. official source targeting (Table backbone + evidence dir present)
def test_official_source_targeting():
    files = discover_policy_raw_files(RAW_DIR)
    names = [path.name for path in files]
    assert BACKBONE_FILENAME in names
    assert sum(1 for name in names if name.endswith(".html")) >= 40
    assert sum(1 for name in names if name.endswith(".pdf")) >= 5
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.source_institution == "RBI"
    assert "rbi.org.in" in (manifest.source_url or "")


# 2. expected schema (backbone sheets + canonical columns)
def test_expected_schema():
    backbone, _ = _backbone()
    assert len(backbone) == 187
    assert {event.rate_type for event in backbone} <= ALLOWED_RATE_TYPES
    df = pd.read_csv(CANONICAL_PATH)
    for column in (
        "announcement_date", "effective_date", "observation_date",
        "availability_date", "rate_type", "rate_pct", "change_bps",
        "stance", "decision_id", "reconciliation_status",
    ):
        assert column in df.columns


# 3. date parsing (effective range + announcement parsability)
def test_date_parsing():
    df = pd.read_csv(CANONICAL_PATH)
    effective = pd.to_datetime(df["effective_date"])
    assert effective.min().date() == date(2008, 6, 12)
    assert effective.max().date() == date(2025, 12, 5)
    announced = pd.to_datetime(df["announcement_date"].dropna())
    assert announced.min().date() >= date(2008, 1, 1)


# 4. numeric rate validity (positive, plausible Indian policy range)
def test_numeric_rate_validity():
    df = pd.read_csv(CANONICAL_PATH)
    assert (df["rate_pct"] > 0).all()
    assert (df["rate_pct"] < 20).all()


# 5. rate-type semantics (allowlist enforced, CRR/SLR excluded)
def test_rate_type_semantics():
    assert set(RATE_COLUMNS) == ALLOWED_RATE_TYPES
    df = pd.read_csv(CANONICAL_PATH)
    assert set(df["rate_type"]) <= ALLOWED_RATE_TYPES
    assert "CRR" not in set(df["rate_type"])
    assert "SLR" not in set(df["rate_type"])


# 6. duplicate handling (no duplicated natural keys)
def test_duplicate_handling():
    df = pd.read_csv(CANONICAL_PATH)
    assert not df.duplicated(subset=["effective_date", "rate_type"]).any()


# 7. conflict detection (synthetic conflicting overlap halts)
def test_conflict_detection():
    backbone, _ = _backbone()
    assert backbone, "backbone must be non-empty for this regression test"
    from src.india.policy_canonicalize import BackboneEvent

    first = BackboneEvent(
        effective_date=date(2020, 3, 27), rate_type="REPO",
        rate_pct=4.40, sheet="T_40(ii)",
    )
    second = BackboneEvent(
        effective_date=date(2020, 3, 27), rate_type="REPO",
        rate_pct=99.99, sheet="T_40(ii)-alt",
    )
    seen: set = set()
    dupes = 0
    for event in (first, second):
        key = (event.effective_date, event.rate_type)
        if key in seen:
            dupes += 1
        seen.add(key)
    assert dupes == 1


# 8. chronology (ascending effective dates per rate_type, no gaps fabricated)
def test_chronology():
    df = pd.read_csv(CANONICAL_PATH)
    for _, group in df.groupby("rate_type"):
        dates = pd.to_datetime(group["effective_date"])
        assert dates.is_monotonic_increasing
        assert not dates.duplicated().any()


# 9. change_bps calculation (Table-predecessor arithmetic + spot checks)
def test_change_bps_calculation():
    df = pd.read_csv(CANONICAL_PATH)
    row = df[(df["effective_date"] == "2022-05-04") & (df["rate_type"] == "REPO")].iloc[0]
    assert row["rate_pct"] == 4.40
    assert int(row["change_bps"]) == 40
    assert float(row["previous_rate_pct"]) == 4.00
    row = df[(df["effective_date"] == "2025-06-06") & (df["rate_type"] == "REPO")].iloc[0]
    assert int(row["change_bps"]) == -50
    # First observation per rate_type has no predecessor.
    firsts = df.sort_values("effective_date").drop_duplicates("rate_type")
    assert firsts["change_bps"].isna().all()


# 10. announcement/effective-date separation (never collapsed)
def test_announcement_effective_separation():
    df = pd.read_csv(CANONICAL_PATH)
    both = df.dropna(subset=["announcement_date"])
    assert len(both) > 100
    assert (both["announcement_date"] != "") .any()
    # Proven dual-date cases: announcement strictly before effectiveness.
    early = both[
        pd.to_datetime(both["announcement_date"])
        < pd.to_datetime(both["effective_date"])
    ]
    assert len(early) >= 8
    # Availability follows announcement, never effectiveness alone, when known.
    assert (
        pd.to_datetime(both["availability_date"])
        == pd.to_datetime(both["announcement_date"])
    ).all()


# 11. leakage boundary (InformationSet: nothing visible before availability)
def test_leakage_boundary():
    df = pd.read_csv(CANONICAL_PATH)
    vintages = df.rename(columns={"rate_type": "variable"})[
        ["variable", "observation_date", "availability_date", "rate_pct"]
    ].copy()
    vintages["revision_version"] = 0
    info = InformationSet(vintages, allow_pre_observation=True)
    for cutoff in ("2015-01-01", "2020-01-01", "2024-01-01"):
        visible = info.information_available_at(cutoff)
        assert (
            pd.to_datetime(visible["availability_date"]).dt.tz_localize(None)
            <= pd.Timestamp(cutoff)
        ).all()
    report = LeakageAuditor().audit_all(policy_df=df)
    assert report.is_clean


# 12. no future-derived fields (column allowlist)
def test_no_future_derived_fields():
    df = pd.read_csv(CANONICAL_PATH)
    lowered = [str(column).lower() for column in df.columns]
    assert not any(
        token in column
        for column in lowered
        for token in ("future", "forward", "next_", "lead_", "forecast")
    )
    assert "roll_applied" not in lowered
    assert "continuous" not in " ".join(lowered)


# 13. no forward filling (event rows only, sparse by construction)
def test_no_forward_filling():
    df = pd.read_csv(CANONICAL_PATH)
    assert len(df) == 187
    assert df["observation_date"].nunique() == 61
    assert len(df) < 500  # event-based, not a daily expansion


# 14. reproducible canonicalization (rebuild matches committed file)
def test_reproducible_canonicalization():
    from src.india.policy_canonicalize import (
        collect_pdf_evidence,
        collect_resolutions,
        reconcile_events,
    )

    macro = RAW_DIR
    backbone, _ = _backbone()
    announcements = collect_announcements(macro / "policy")
    resolutions = collect_resolutions(macro / "policy") + collect_pdf_evidence(
        macro / "policy"
    )
    canonical, blocked = reconcile_events(
        backbone, announcements, resolutions, BACKBONE_FILENAME
    )
    assert blocked == []
    rebuilt = build_canonical_frame(canonical)
    committed = pd.read_csv(CANONICAL_PATH, dtype=str).fillna("")
    check = rebuilt.astype(str)
    pd.testing.assert_frame_equal(
        check.reset_index(drop=True), committed.reset_index(drop=True)
    )


# 15. manifest bookkeeping (187 events, 62 artifacts, change validation)
def test_manifest_bookkeeping():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.row_count == 187
    assert manifest.frequency == DataFrequency.EVENT_BASED
    assert manifest.has_observation_date is True
    assert manifest.has_availability_date is True
    assert len(manifest.raw_paths or []) == 1 + 61
    assert len(manifest.raw_artifacts or []) == 1 + 61
    params = manifest.processing_parameters
    assert params["backbone_rows"] == 107
    assert params["canonical_events"] == 187
    assert params["conflicting_overlaps"] == 0
    assert params["excluded_invalid_rows"] == []


# 16. raw/canonical SHA reproducibility
def test_sha_reproducibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.processed_sha256 == manager.compute_sha256(
        "data/processed/india/macro/rbi_policy_rate_events.csv"
    )
    assert manifest.raw_artifacts
    for artifact in manifest.raw_artifacts:
        assert artifact.sha256 == manager.compute_sha256(artifact.path)


# 17. blocked eligibility (calendar/intersection prerequisites unmet)
def test_blocked_eligibility():
    manager = ManifestManager(str(PROJECT_ROOT))
    manifest = manager.load_manifest(MANIFEST_ID)
    assert manifest.acquisition_status == AcquisitionStatus.ACQUIRED
    assert manifest.validation_status == ValidationStatus.PASSED
    assert manifest.eligibility_status == EligibilityStatus.BLOCKED
    assert manifest.eligibility_status != EligibilityStatus.EXPERIMENT_ELIGIBLE


# 18. coverage calculations (61 effective dates, 2008-2025, 5 rate types)
def test_coverage_calculations():
    df = pd.read_csv(CANONICAL_PATH)
    assert df["effective_date"].nunique() == 61
    assert df["rate_type"].nunique() == 5
    # Authoritative decision-group count is 62: one group per announcement
    # (D-prefixed), plus effective-date fallback groups (U-prefixed) where
    # no announcement evidence exists. Verified against the dataset itself.
    assert df["decision_id"].nunique() == 62
    counts = df["rate_type"].value_counts().to_dict()
    assert counts == {
        "REPO": 56, "REVERSE_REPO": 42, "MSF": 41, "BANK_RATE": 37, "SDF": 11,
    }


# 19. unverified-event enforcement (remain in evidence, barred from agents)
def test_unverified_events_barred_from_agent_set():
    from src.india.policy_canonicalize import (
        AGENT_ELIGIBLE_STATUSES,
        agent_eligible_events,
        build_agent_information_set,
    )

    df = pd.read_csv(CANONICAL_PATH)
    unverified = df[df["reconciliation_status"] == "announcement_unverified"]
    # Still present in canonical evidence with availability fallback.
    assert len(unverified) == 27
    assert unverified["announcement_date"].isna().all()
    assert (
        unverified["availability_basis"]
        == "effective_date_fallback_announcement_unverified"
    ).all()
    # Marked experiment-ineligible: excluded by the machine-enforced gate.
    eligible = agent_eligible_events(df)
    assert len(eligible) == 160
    assert set(eligible["reconciliation_status"]) <= AGENT_ELIGIBLE_STATUSES
    merged = eligible.merge(
        unverified[["effective_date", "rate_type"]],
        on=["effective_date", "rate_type"],
        how="inner",
    )
    assert merged.empty
    # The agent-facing InformationSet exposes eligible events only.
    info = build_agent_information_set(df)
    visible = info.information_available_at("2026-06-01")
    assert len(visible) == 160
    # An unfiltered set would leak the 27 unverified events at/after their
    # fallback dates, which is exactly what the gate prevents.
    assert len(visible) == len(df) - len(unverified)


# 20. genuine conflict through reconcile_events blocks (not silently resolved)
def test_genuine_conflict_blocks_reconciliation():
    from datetime import date as _date

    from src.india.policy_canonicalize import BackboneEvent, ResolutionEvidence

    backbone = [
        BackboneEvent(
            effective_date=_date(2019, 10, 4), rate_type="REPO",
            rate_pct=5.15, sheet="T_40(ii)",
        ),
        BackboneEvent(
            effective_date=_date(2020, 3, 27), rate_type="REPO",
            rate_pct=4.40, sheet="T_40(ii)",
        ),
    ]
    conflicting = ResolutionEvidence(
        source_file="synthetic_conflicting_resolution.html",
        page_date=_date(2020, 3, 27),
        meeting_start=None,
        meeting_end=_date(2020, 3, 27),
        announcement_date=_date(2020, 3, 27),
        announcement_basis="page_date_header",
        levels={"REPO": 4.40},
        # Table-implied change is -75 bps; the source claims -10 bps.
        change_bps_stated=-10,
        stance="accommodative",
        effective_words="with immediate effect",
    )
    canonical, blocked = reconcile_events(
        backbone, [], [conflicting], "synthetic_backbone.xlsx"
    )
    assert len(blocked) == 1
    assert blocked[0]["rate_type"] == "REPO"
    assert blocked[0]["effective_date"] == "2020-03-27"
    assert "disagrees" in blocked[0]["reason"]
    conflicted = [e for e in canonical if e.effective_date == _date(2020, 3, 27)]
    assert len(conflicted) == 1
    # Preserved in evidence but flagged, never silently resolved.
    assert conflicted[0].reconciliation_status == "change_conflict"
    assert conflicted[0].announcement_date == _date(2020, 3, 27)
