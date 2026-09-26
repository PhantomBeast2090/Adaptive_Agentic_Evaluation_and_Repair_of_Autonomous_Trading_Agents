"""E5a attribution tests: schema, PIT, attribution, NOOP, reproducibility.

Heavy-data note: tests constructing DecisionAttributionEngine touch the
canonical CSVs through InformationLookup. They reuse one module-scoped
engine instance to avoid repeated ~1GB NSE parses.
"""

import pytest

from evaluation.attribution.engine import (
    BLOCKED,
    DECIDABLE,
    NOT_APPLICABLE,
    NO_ORDERS,
    UNDECIDABLE_MISSING_LEG,
    DecisionAttributionEngine,
    deterministic_decision_id,
    instrument_filter,
)
from evaluation.attribution.persistence import flatten_attribution


@pytest.fixture(scope="module")
def engine():
    return DecisionAttributionEngine(base_dir=".")


def _order_record(dec_time="2023-05-16"):
    return {
        "decision_timestamp": dec_time,
        "state_fingerprint": "hash123",
        "submitted_orders": [
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "side": "BUY",
                "requested_quantity": 10.0,
            }
        ],
        "validation": [
            {
                "status": "VALIDATED",
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "side": "BUY",
                "requested_quantity": 10.0,
            }
        ],
        "executions": [
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "execution_status": "EXECUTED_FULL",
                "execution_price": 2500.0,
                "transaction_cost": 1.0,
            }
        ],
        "portfolio_before": {"cash": 100000.0, "total_equity": 100000.0},
        "portfolio_after": {"cash": 75000.0, "total_equity": 100000.0},
        "environment_metadata": {"market_fingerprint": "envhash1"},
    }


def _noop_record(dec_time="2023-05-16"):
    return {
        "decision_timestamp": dec_time,
        "state_fingerprint": "hash456",
        "submitted_orders": [],
        "validation": [],
        "executions": [],
        "portfolio_before": {"cash": 100000.0, "total_equity": 100000.0},
        "portfolio_after": {"cash": 100000.0, "total_equity": 100000.0},
        "environment_metadata": {"market_fingerprint": "envhash1"},
    }


# -- schema / deterministic IDs ------------------------------------------

def test_deterministic_decision_id_stable():
    a = deterministic_decision_id("exp", "ep", "2023-05-16",
                                  "nse_equity", "RELIANCE:EQ", 0)
    b = deterministic_decision_id("exp", "ep", "2023-05-16",
                                  "nse_equity", "RELIANCE:EQ", 0)
    c = deterministic_decision_id("exp", "ep", "2023-05-16",
                                  "nse_equity", "RELIANCE:EQ", 1)
    assert a == b
    assert a != c


def test_instrument_filter_matches_environment():
    assert instrument_filter("nse_equity", "RELIANCE:EQ") == {
        "symbol": "RELIANCE", "series": "EQ"}
    assert instrument_filter("mcx_gold", "GOLDAUG2023") == {
        "contract_symbol": "GOLDAUG2023"}
    assert instrument_filter("nifty50", "nifty50") is None
    with pytest.raises(ValueError):
        instrument_filter("nse_equity", "MALFORMED")


# -- NOOP / participation semantics ---------------------------------------

def test_noop_row_preserved_not_opportunity(engine):
    result = engine.attribute_trajectory(
        decision_records=[_noop_record()],
        episode_id="ep1", arm="A", trajectory_fingerprint="traj",
        run_id="run1", experiment_id="exp1",
        experiment_grid=["2023-05-15", "2023-05-16", "2023-05-17"],
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert len(result.attributed_decisions) == 1
    row = result.attributed_decisions[0]
    assert row.participation_status == NO_ORDERS
    assert row.attribution_status == NOT_APPLICABLE
    assert row.outcomes.opportunity_return is None
    assert row.outcomes.mae is None and row.outcomes.mfe is None


def test_blocked_order_marked_not_adverse(engine):
    rec = _order_record()
    rec["executions"] = []
    rec["validation"] = [{
        "status": "NOOP_MARKET_CLOSED", "asset_id": "nse_equity",
        "instrument": "RELIANCE:EQ", "side": "BUY",
        "requested_quantity": 10.0}]
    result = engine.attribute_trajectory(
        decision_records=[rec],
        episode_id="ep1", arm="A", trajectory_fingerprint="traj",
        run_id="run1", experiment_id="exp1",
        experiment_grid=["2023-05-15", "2023-05-16", "2023-05-17"],
        created_at="2026-01-01T00:00:00+00:00",
    )
    row = result.attributed_decisions[0]
    assert row.participation_status.startswith(BLOCKED)
    assert row.outcomes.opportunity_return is None


# -- PIT: pre-trend never touches decision-bar or future -------------------

def test_pre_trend_pit_pure_with_controlled_frames(engine, monkeypatch):
    closes = {
        "2023-05-10": 100.0, "2023-05-11": 110.0, "2023-05-12": 121.0,
        "2023-05-15": 200.0,  # decision bar: must NOT enter pre-trend
        "2023-05-16": 999.0,  # future: must NOT enter pre-trend
    }
    monkeypatch.setattr(engine, "_close",
                        lambda a, i, s: closes.get(s))
    monkeypatch.setattr(engine, "_ohlc", lambda a, i, s: None)
    monkeypatch.setattr(engine, "_pit_snapshot", lambda a, i, t: {})
    grid = ["2023-05-10", "2023-05-11", "2023-05-12",
            "2023-05-15", "2023-05-16"]
    rec = _order_record("2023-05-15")
    result = engine.attribute_trajectory(
        decision_records=[rec],
        episode_id="ep1", arm="A", trajectory_fingerprint="traj",
        run_id="run1", experiment_id="exp1",
        experiment_grid=grid,
        created_at="2026-01-01T00:00:00+00:00",
    )
    row = result.attributed_decisions[0]
    # pre_1d = (121-110)/110 from t-1/t-2 only
    assert row.outcomes.pre_trend_1d == pytest.approx((121.0 - 110.0) / 110.0)
    assert row.outcomes.pre_trend_1d != pytest.approx((200.0 - 121.0) / 121.0)


def test_forward_return_uses_execution_price(engine, monkeypatch):
    closes = {"2023-05-15": 200.0, "2023-05-16": 210.0,
              "2023-05-18": 230.0}
    monkeypatch.setattr(engine, "_close",
                        lambda a, i, s: closes.get(s))
    monkeypatch.setattr(engine, "_ohlc", lambda a, i, s: None)
    monkeypatch.setattr(engine, "_pit_snapshot", lambda a, i, t: {})
    grid = ["2023-05-15", "2023-05-16", "2023-05-17", "2023-05-18"]
    rec = _order_record("2023-05-15")  # exec price 2500.0
    result = engine.attribute_trajectory(
        decision_records=[rec],
        episode_id="ep1", arm="A", trajectory_fingerprint="traj",
        run_id="run1", experiment_id="exp1",
        experiment_grid=grid,
        created_at="2026-01-01T00:00:00+00:00",
    )
    row = result.attributed_decisions[0]
    assert row.outcomes.forward_return_1d == pytest.approx((210.0 - 2500.0) / 2500.0)
    assert row.outcomes.opportunity_return == pytest.approx(
        row.outcomes.forward_return_3d)  # BUY: opportunity == fwd_3d


def test_mae_mfe_buy_sell_sign(engine, monkeypatch):
    bars = {
        "2023-05-16": {"high": 2600.0, "low": 2400.0},
        "2023-05-17": {"high": 2700.0, "low": 2300.0},
        "2023-05-18": {"high": 2550.0, "low": 2450.0},
    }

    def fake_close(a, i, s):
        return {"2023-05-15": 2500.0, "2023-05-18": 2400.0}.get(s)

    monkeypatch.setattr(engine, "_close", fake_close)
    monkeypatch.setattr(engine, "_ohlc",
                        lambda a, i, s: bars.get(s))
    monkeypatch.setattr(engine, "_pit_snapshot", lambda a, i, t: {})
    grid = ["2023-05-15", "2023-05-16", "2023-05-17", "2023-05-18"]
    buy = engine.attribute_trajectory(
        decision_records=[_order_record("2023-05-15")],
        episode_id="ep1", arm="A", trajectory_fingerprint="t",
        run_id="r", experiment_id="e", experiment_grid=grid,
        created_at="2026-01-01T00:00:00+00:00",
    ).attributed_decisions[0]
    assert buy.outcomes.mae == pytest.approx((2300.0 - 2500.0) / 2500.0)
    assert buy.outcomes.mfe == pytest.approx((2700.0 - 2500.0) / 2500.0)

    sell_rec = _order_record("2023-05-15")
    sell_rec["submitted_orders"][0]["side"] = "SELL"
    sell = engine.attribute_trajectory(
        decision_records=[sell_rec],
        episode_id="ep1", arm="A", trajectory_fingerprint="t",
        run_id="r", experiment_id="e", experiment_grid=grid,
        created_at="2026-01-01T00:00:00+00:00",
    ).attributed_decisions[0]
    assert sell.outcomes.mae == pytest.approx((2500.0 - 2700.0) / 2500.0)
    assert sell.outcomes.opportunity_return == pytest.approx(
        -sell.outcomes.forward_return_3d)


def test_real_runner_shapes_prefixed_instrument_and_quantity_key(engine):
    """Regression: orders carry quantity + bare instrument; executions
    carry requested_quantity + asset-prefixed instrument."""
    rec = {
        "decision_timestamp": "2023-05-16",
        "state_fingerprint": "h",
        "submitted_orders": [
            {"asset_id": "nse_equity", "instrument": "TCS:EQ",
             "quantity": 1.0, "side": "BUY"},
        ],
        "validation": [
            {"status": "VALIDATED", "asset_id": "nse_equity",
             "instrument": "TCS:EQ", "side": "BUY",
             "requested_quantity": 1.0},
        ],
        "executions": [
            {"asset_id": "nse_equity",
             "instrument": "nse_equity:TCS:EQ",
             "execution_status": "EXECUTED_FULL",
             "execution_price": 3255.05, "transaction_cost": 1.6,
             "requested_quantity": 1.0, "executed_quantity": 1.0},
        ],
        "portfolio_before": {"cash": 1.0, "total_equity": 1.0},
        "portfolio_after": {"cash": 1.0, "total_equity": 1.0},
        "environment_metadata": {"market_fingerprint": "m"},
    }
    row = engine.attribute_trajectory(
        decision_records=[rec],
        episode_id="ep", arm="A", trajectory_fingerprint="t",
        run_id="r", experiment_id="e",
        experiment_grid=["2023-05-15", "2023-05-16", "2023-05-17"],
        created_at="2026-01-01T00:00:00+00:00").attributed_decisions[0]
    assert row.decision_time_state.quantity == 1.0
    assert row.decision_time_state.execution_price == 3255.05
    assert row.participation_status == "EXECUTED"


# -- reproducibility --------------------------------------------------------

def test_same_input_same_output_and_fingerprint(engine):
    kwargs = dict(
        decision_records=[_order_record(), _noop_record("2023-05-17")],
        episode_id="ep1", arm="A", trajectory_fingerprint="traj",
        run_id="run1", experiment_id="exp1",
        experiment_grid=["2023-05-15", "2023-05-16", "2023-05-17",
                         "2023-05-18", "2023-05-19"],
    )
    r1 = engine.attribute_trajectory(
        created_at="2026-01-01T00:00:00+00:00", **kwargs)
    r2 = engine.attribute_trajectory(
        created_at="2026-06-01T00:00:00+00:00", **kwargs)
    assert [d.decision_id for d in r1.attributed_decisions] == \
           [d.decision_id for d in r2.attributed_decisions]
    assert r1.fingerprint() == r2.fingerprint()
    assert r1.to_dict()["created_at"] != r2.to_dict()["created_at"]


def test_arm_agnostic(engine):
    recs = [_order_record()]
    grid = ["2023-05-15", "2023-05-16", "2023-05-17"]
    rows_a = engine.attribute_trajectory(
        decision_records=recs, episode_id="ep", arm="A",
        trajectory_fingerprint="t", run_id="r", experiment_id="e",
        experiment_grid=grid,
        created_at="2026-01-01T00:00:00+00:00").attributed_decisions
    rows_b = engine.attribute_trajectory(
        decision_records=recs, episode_id="ep", arm="B",
        trajectory_fingerprint="t", run_id="r", experiment_id="e",
        experiment_grid=grid,
        created_at="2026-01-01T00:00:00+00:00").attributed_decisions
    assert rows_a[0].outcomes == rows_b[0].outcomes
    assert rows_a[0].arm == "A" and rows_b[0].arm == "B"


def test_flatten_produces_decision_table(engine):
    result = engine.attribute_trajectory(
        decision_records=[_order_record(), _noop_record("2023-05-17")],
        episode_id="ep1", arm="A", trajectory_fingerprint="traj",
        run_id="run1", experiment_id="exp1",
        experiment_grid=["2023-05-15", "2023-05-16", "2023-05-17",
                         "2023-05-18"],
        created_at="2026-01-01T00:00:00+00:00",
    )
    rows = flatten_attribution(result.to_dict())
    assert len(rows) == 2
    required = {"experiment_id", "decision_id", "decision_timestamp",
                "instrument", "action", "quantity", "execution_price",
                "pre_trend_1d", "pre_trend_3d", "pre_trend_5d",
                "forward_return_1d", "forward_return_3d", "mae", "mfe",
                "hold_return", "opportunity_return", "participation_status",
                "attribution_status"}
    assert required <= set(rows[0].keys())
