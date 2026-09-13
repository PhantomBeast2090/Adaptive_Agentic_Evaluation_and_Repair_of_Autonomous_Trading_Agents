"""C. Temporal lookup + D. PIT visibility + E. Calendar applicability tests."""

from environment.indian.information_lookup import (
    STATUS_AVAILABLE,
    STATUS_CONSTRAINT_FAIL,
    STATUS_INFO_UNAVAILABLE,
    STATUS_OBS_MISSING,
)


def test_lookup_before_any_bar_is_obs_missing(indian_env):
    slot = indian_env.lookup.get_information("nifty50", "1990-01-01", "explicit")
    assert slot.status == STATUS_OBS_MISSING


def test_lookup_unparseable_timestamp_is_constraint_fail(indian_env):
    slot = indian_env.lookup.get_information("nifty50", "not-a-date", "explicit")
    assert slot.status == STATUS_CONSTRAINT_FAIL


def test_future_availability_invisible_cpi(indian_env):
    # April-2023 CPI (available 2023-06-12) must not show on 2023-05-15.
    slot = indian_env.lookup.get_information("cpi", "2023-05-15", "explicit")
    assert slot.status == STATUS_AVAILABLE
    assert slot.observation_date == "2023-03-31"


def test_historical_availability_visible(indian_env):
    # 2023-05 provisional (available 2023-06-12) is the latest eligible
    # vintage on 2023-06-15; the 2023-05 final (available 07-12) is not.
    slot = indian_env.lookup.get_information("cpi", "2023-06-15", "explicit")
    assert slot.status == STATUS_AVAILABLE
    assert slot.observation_date == "2023-05-31"
    assert slot.availability_date == "2023-06-12"


def test_null_availability_invisible_under_strict_pit(indian_env):
    slot = indian_env.lookup.get_information("brent", "2023-05-15", "explicit")
    assert slot.status == STATUS_INFO_UNAVAILABLE


def test_publication_asset_bypasses_calendar_gate(indian_env):
    # MOSPI venue has no calendar rows by design; CPI still resolves.
    slot = indian_env.lookup.get_information("cpi", "2023-05-15", "explicit")
    assert slot.status == STATUS_AVAILABLE
    assert slot.venue == "MOSPI"


def test_same_date_bar_never_visible(indian_env):
    # 2023-05-15 NIFTY bar exists but must be invisible AT 2023-05-15.
    slot = indian_env.lookup.get_information("nifty50", "2023-05-15", "explicit")
    assert slot.status == STATUS_AVAILABLE
    assert slot.observation_date == "2023-05-12"


def test_policy_event_visibility_follows_announcement(indian_env):
    slot = indian_env.lookup.get_information("rbi_policy", "2023-05-15", "explicit")
    assert slot.status == STATUS_AVAILABLE
    assert slot.availability_date <= "2023-05-15"


def test_lookup_provenance_reports_coverage(indian_env):
    prov = indian_env.lookup.provenance("cpi")
    assert prov["rows"] == 209
    assert prov["lookup_path"] == "vintage_pit"
    prov2 = indian_env.lookup.provenance("nifty50")
    assert prov2["lookup_path"] == "observation_lag"
