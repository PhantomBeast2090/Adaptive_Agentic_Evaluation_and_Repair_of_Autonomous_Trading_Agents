"""E2-B authority tests (mandate points 35-39)."""

from evaluation.diagnostics.execution import execute

from .execution_fixtures import (
    BuyOnceAgent,
    HoldAgent,
    OutsideUniverseAgent,
    baseline_spec,  # noqa: F401
    make_episode_config,
    make_exec_state,
)


def test_configured_universe_still_enforced(baseline_spec):
    state = make_exec_state(baseline_spec, "D-AUTH-1")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=OutsideUniverseAgent(),
        episode_config=make_episode_config(seed=31),
    )
    assert episode.result.status.value == "COMPLETED"
    for record in episode.decision_records:
        assert (
            record.executions[0]["execution_status"]
            == "NOOP_INSTRUMENT_OUTSIDE_UNIVERSE"
        )
    assert episode.result.measured_by_name("turnover").value == 0.0


def test_calendar_semantics_unchanged(baseline_spec):
    state = make_exec_state(baseline_spec, "D-AUTH-2")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=BuyOnceAgent(),
        episode_config=make_episode_config(seed=32),
    )
    by_instrument = {}
    for record in episode.decision_records:
        for execution in record.executions:
            by_instrument.setdefault(
                execution["instrument"], execution["execution_status"]
            )
    # No gold was ordered; the episode holds only the equity fill.
    assert by_instrument == {"nse_equity:RELIANCE:EQ": "EXECUTED_FULL"}
    market_fps = {
        record.environment_metadata["market_fingerprint"]
        for record in episode.decision_records
    }
    assert market_fps == {state.environment_spec["market_fingerprint"]}


def test_pit_vintage_and_visibility_semantics(baseline_spec):
    state = make_exec_state(baseline_spec, "D-AUTH-3")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=33),
    )
    first = episode.decision_records[0]
    # Brent stays unavailable (NULL availability under strict PIT);
    # RBI reference FX is visible through the lag path.
    assert "brent" in first.unavailable_assets
    assert "usd_inr" in first.visible_assets
    assert "nifty50" in first.visible_assets
    assert "indiavix" in first.visible_assets


def test_multi_asset_visibility_semantics(baseline_spec):
    state = make_exec_state(baseline_spec, "D-AUTH-4")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=34),
    )
    first = episode.decision_records[0]
    market_visible = {
        key for key in first.visible_assets if not key.startswith("brent")
    }
    assert "nse_equity:RELIANCE:EQ" in first.visible_assets
    assert "nse_equity:TCS:EQ" in first.visible_assets
    assert "mcx_gold:GOLDAUG2023" in first.visible_assets
    assert len(market_visible) >= 6
    for macro in (
        "gsec10y",
        "tbill91d",
        "tbill364d",
        "rbi_policy",
        "cpi",
        "iip",
    ):
        assert macro in first.visible_assets or macro in first.unavailable_assets


def test_gold_order_fails_closed_on_unknown_calendar(baseline_spec):
    from evaluation.contracts.agent import AgentIdentity
    from evaluation.contracts.oracle import TargetObservation

    class GoldAgent:
        identity = AgentIdentity("gold-stub", "0.1")

        def reset(self):
            return None

        def act(self, observation):
            if not isinstance(observation, TargetObservation):
                raise TypeError("stub accepts only TargetObservation")
            return [
                {
                    "asset_id": "mcx_gold",
                    "instrument": "GOLDAUG2023",
                    "side": "BUY",
                    "quantity": 1.0,
                }
            ]

    state = make_exec_state(baseline_spec, "D-AUTH-5")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=GoldAgent(),
        episode_config=make_episode_config(seed=35),
    )
    for record in episode.decision_records:
        assert (
            record.executions[0]["execution_status"] == "NOOP_UNKNOWN_CALENDAR"
        )
