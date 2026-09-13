"""Focused tests B: explicit vintage availability handling."""

import pandas as pd
import pytest

from src.india.experiment_intersection import build_requirement_from_frame
from src.india.information_set import InformationSet


def _vintage_frame():
    # January CPI with provisional (Feb-12) and final (Mar-12) vintages.
    return pd.DataFrame({
        "observation_date": ["2025-01-31", "2025-01-31"],
        "availability_date": ["2025-02-12", "2025-03-12"],
        "revision_version": [0, 1],
        "value": [100.0, 101.0],
    })


def test_b1_single_availability_value_needs_no_policy():
    frame = pd.DataFrame({
        "observation_date": ["2025-01-31"],
        "availability_date": ["2025-02-12"],
        "revision_version": [0],
    })
    req = build_requirement_from_frame(
        asset_id="cpi", venue="MOSPI", frame=frame,
        observation_col="observation_date",
        availability_col="availability_date",
        requires_calendar=False)
    assert req.availability_by_date == {"2025-01-31": "2025-02-12"}


def test_b2_multiple_vintages_without_policy_raise():
    with pytest.raises(ValueError, match="explicit availability_policy"):
        build_requirement_from_frame(
            asset_id="cpi", venue="MOSPI", frame=_vintage_frame(),
            observation_col="observation_date",
            availability_col="availability_date",
            requires_calendar=False)


def test_b3_earliest_available_policy():
    req = build_requirement_from_frame(
        asset_id="cpi", venue="MOSPI", frame=_vintage_frame(),
        observation_col="observation_date",
        availability_col="availability_date",
        requires_calendar=False,
        availability_policy="earliest_available")
    assert req.availability_by_date == {"2025-01-31": "2025-02-12"}


def test_b4_latest_available_policy():
    req = build_requirement_from_frame(
        asset_id="cpi", venue="MOSPI", frame=_vintage_frame(),
        observation_col="observation_date",
        availability_col="availability_date",
        requires_calendar=False,
        availability_policy="latest_available")
    assert req.availability_by_date == {"2025-01-31": "2025-03-12"}


def test_b5_explicit_mapping_respected_exactly():
    from src.india.experiment_intersection import AssetRequirement
    req = AssetRequirement(
        asset_id="cpi", venue="MOSPI",
        observation_dates=frozenset(["2025-01-31"]),
        availability_by_date={"2025-01-31": "2025-03-12"},
        requires_calendar=False)
    assert req.availability_by_date == {"2025-01-31": "2025-03-12"}


def test_b6_null_only_availability_stays_null_strict_rejects():
    frame = pd.DataFrame({
        "observation_date": ["2025-01-31", "2025-01-31"],
        "availability_date": [None, None],
        "revision_version": [0, 1],
    })
    req = build_requirement_from_frame(
        asset_id="brent", venue="EIA", frame=frame,
        observation_col="observation_date",
        availability_col="availability_date",
        requires_calendar=False)
    assert req.availability_by_date == {"2025-01-31": None}


def test_b7_pre_observation_rule_still_applies():
    from src.india.temporal_eligibility import check_row_eligibility
    frame = pd.DataFrame({
        "observation_date": ["2025-01-31"],
        "availability_date": ["2025-01-15"],
        "revision_version": [0],
    })
    req = build_requirement_from_frame(
        asset_id="cpi", venue="MOSPI", frame=frame,
        observation_col="observation_date",
        availability_col="availability_date",
        requires_calendar=False)
    verdict = check_row_eligibility(
        req.availability_by_date["2025-01-31"], "2025-02-01",
        strict=True, allow_pre_observation=False,
        observation_date="2025-01-31")
    assert not verdict.eligible and verdict.reason_code == "CONSTRAINT_FAIL"


def test_b8_informationset_behavior_unchanged():
    vintages = pd.DataFrame({
        "variable": ["CPI", "CPI"],
        "observation_date": ["2025-01-31", "2025-01-31"],
        "availability_date": ["2025-02-12", "2025-03-12"],
        "revision_version": [0, 1],
        "value": [100.0, 101.0],
    })
    info = InformationSet(vintages)
    assert info.information_available_at("2025-02-15").iloc[0]["value"] == 100.0
    assert info.information_available_at("2025-03-15").iloc[0]["value"] == 101.0


def test_b9_deterministic_across_repeated_calls():
    kwargs = dict(asset_id="cpi", venue="MOSPI", frame=_vintage_frame(),
                  observation_col="observation_date",
                  availability_col="availability_date",
                  requires_calendar=False,
                  availability_policy="earliest_available")
    first = build_requirement_from_frame(**kwargs)
    second = build_requirement_from_frame(**kwargs)
    assert first == second
    assert dict(first.availability_by_date) == dict(second.availability_by_date)


def test_b10_unknown_policy_rejected():
    with pytest.raises(ValueError, match="Unknown availability_policy"):
        build_requirement_from_frame(
            asset_id="cpi", venue="MOSPI", frame=_vintage_frame(),
            observation_col="observation_date",
            availability_col="availability_date",
            availability_policy="newest_ish")
