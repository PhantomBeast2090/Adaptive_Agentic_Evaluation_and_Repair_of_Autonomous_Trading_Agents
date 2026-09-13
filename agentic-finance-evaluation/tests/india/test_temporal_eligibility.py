"""Focused tests: temporal eligibility (obs vs availability vs decision)."""

import pandas as pd

from src.india.temporal_eligibility import (
    check_row_eligibility,
    eligible_frame,
)


def test_known_availability_before_decision_is_eligible():
    d = check_row_eligibility("2024-02-12", "2024-03-01")
    assert d.eligible and d.reason_code == "OK"


def test_availability_after_decision_is_temporal_leakage():
    d = check_row_eligibility("2024-03-12", "2024-03-01")
    assert not d.eligible and d.reason_code == "INFO_UNAVAILABLE"


def test_null_availability_strict_is_ineligible():
    for null in (None, "", float("nan")):
        d = check_row_eligibility(null, "2024-03-01", strict=True)
        assert not d.eligible and d.reason_code == "INFO_UNAVAILABLE", repr(null)


def test_policy_pre_observation_semantics():
    # RBI policy: announcement may precede effective date (e.g. Jun-2008).
    d = check_row_eligibility(
        "2008-06-11", "2008-06-11", allow_pre_observation=True,
        observation_date="2008-06-12",
    )
    assert d.eligible
    d2 = check_row_eligibility(
        "2008-06-11", "2008-06-11", allow_pre_observation=False,
        observation_date="2008-06-12",
    )
    assert not d2.eligible and d2.reason_code == "CONSTRAINT_FAIL"


def test_eligible_frame_gates_vintages():
    frame = pd.DataFrame({
        "observation_date": ["2024-01-31", "2024-01-31"],
        "availability_date": ["2024-02-12", "2024-03-12"],
        "value": [100.0, 101.0],
    })
    assert eligible_frame(frame, "2024-02-01").empty
    assert len(eligible_frame(frame, "2024-02-15")) == 1
    assert len(eligible_frame(frame, "2024-03-15")) == 2


def test_missing_availability_column_strict_returns_nothing():
    frame = pd.DataFrame({"date": ["2024-01-02"]})
    assert eligible_frame(frame, "2024-02-01", availability_col="availability_date").empty


def test_leakage_auditor_decision_timestamp_gate():
    from src.india.leakage_audit import LeakageAuditor
    frame = pd.DataFrame({"availability_date": pd.to_datetime(["2024-02-12"])})
    out = LeakageAuditor().check_decision_timestamp_eligibility(frame, "2024-02-01")
    assert any(v.severity == "CONFIRMED" for v in out)
    out2 = LeakageAuditor().check_decision_timestamp_eligibility(frame, "2024-03-01")
    assert not any(v.severity == "CONFIRMED" for v in out2)
    # NULL availability under strict PIT blocks use (does not weaken gates)
    null_frame = pd.DataFrame({"availability_date": [None]})
    out3 = LeakageAuditor().check_decision_timestamp_eligibility(null_frame, "2024-03-01")
    assert any(v.severity == "UNRESOLVED" for v in out3)
