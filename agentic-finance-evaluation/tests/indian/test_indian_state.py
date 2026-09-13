"""F. Multi-asset state + G. Missingness tests."""

from environment.indian.information_lookup import STATUS_AVAILABLE


def test_state_blocks_are_typed_and_separate(fresh_env):
    state = fresh_env._state_at(fresh_env.grid[0])
    assert state.decision_timestamp == fresh_env.grid[0].isoformat()
    assert set(state.market) == {
        "nse_equity:RELIANCE:EQ", "nse_equity:TCS:EQ",
        "mcx_gold:GOLDAUG2023", "nifty50", "indiavix", "usd_inr"}
    assert set(state.macro) == {
        "gsec10y", "tbill91d", "tbill364d", "rbi_policy",
        "cpi", "iip", "brent"}
    assert state.portfolio.cash == fresh_env.initial_cash


def test_state_serializes_with_metadata(fresh_env):
    d = fresh_env.reset()
    slot = d["market"]["nse_equity:RELIANCE:EQ"]
    assert set(slot) == {"status", "venue", "observation_date",
                         "availability_date", "vintage", "values", "reason"}
    assert slot["status"] == STATUS_AVAILABLE
    assert slot["venue"] == "NSE_CM"


def test_missingness_distinguishes_reasons(fresh_env):
    missing = fresh_env._state_at(fresh_env.grid[0]).missingness()
    # Brent: exists but never available. Gold slot: bar-lag visible here.
    assert missing["brent"] == "INFO_UNAVAILABLE"
    assert missing["nifty50"] == STATUS_AVAILABLE
    # Every slot reports some explicit reason code, never bare NaN.
    assert set(missing.values()) <= {
        "AVAILABLE", "OBS_MISSING", "INFO_UNAVAILABLE",
        "CAL_UNKNOWN", "CAL_CLOSED", "CONSTRAINT_FAIL"}


def test_brent_never_leaks_into_state_values(fresh_env):
    d = fresh_env.reset()
    assert d["macro"]["brent"]["values"] == {}
    assert d["macro"]["brent"]["observation_date"] is None
