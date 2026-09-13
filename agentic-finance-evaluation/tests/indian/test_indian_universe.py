"""Configured tradable-universe enforcement tests (A-J)."""

import pytest

from environment.indian.actions import (
    STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE,
    STATUS_NOOP_NON_TRADEABLE_ASSET,
    STATUS_NOOP_UNKNOWN_INSTRUMENT,
    validate_orders,
)
from environment.indian.environment import IndianMultiAssetEnvironment
from tests.indian.conftest import SMALL_CONFIG

ALLOWED = {"nse_equity": {"RELIANCE:EQ"}, "mcx_gold": {"GOLDAUG2023"}}


def _order(asset, instrument, side="BUY", qty=1.0):
    return [{"asset_id": asset, "instrument": instrument,
             "side": side, "quantity": qty}]


def test_a_configured_nse_instrument_accepted():
    out = validate_orders(_order("nse_equity", "RELIANCE:EQ"), ALLOWED)
    assert out[0].status == "VALIDATED"


def test_b_valid_canonical_outside_universe_rejected():
    # HDFCBANK:EQ has 1721 canonical bars but is not in this universe.
    out = validate_orders(_order("nse_equity", "HDFCBANK:EQ"), ALLOWED)
    assert out[0].status == STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE


def test_c_configured_gold_accepted_subject_to_gates(fresh_env):
    out = validate_orders(_order("mcx_gold", "GOLDAUG2023"), ALLOWED)
    assert out[0].status == "VALIDATED"
    # Through the environment it then fails closed on the UNKNOWN calendar.
    _, info, _, _ = fresh_env.step(_order("mcx_gold", "GOLDAUG2023"))
    assert info["executions"][0]["execution_status"] == "NOOP_UNKNOWN_CALENDAR"
    fresh_env.reset()


def test_d_valid_gold_contract_outside_universe_rejected():
    out = validate_orders(_order("mcx_gold", "GOLDJUN2023"), ALLOWED)
    assert out[0].status == STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE


def test_e_unknown_instrument_stays_distinguishable():
    out = validate_orders(_order("nse_equity", "RELIANCE", 1.0), ALLOWED)
    assert out[0].status == STATUS_NOOP_UNKNOWN_INSTRUMENT
    out = validate_orders(_order("nse_equity", "", 1.0), ALLOWED)
    assert out[0].status == STATUS_NOOP_UNKNOWN_INSTRUMENT


def test_f_information_assets_still_rejected(fresh_env):
    for aid in ("cpi", "nifty50", "brent"):
        _, info, _, _ = fresh_env.step(_order(aid, "X"))
        assert info["executions"][0]["execution_status"] == STATUS_NOOP_NON_TRADEABLE_ASSET
    fresh_env.reset()


def test_g_config_change_permits_deterministically():
    cfg = dict(SMALL_CONFIG)
    cfg["universe"] = {"nse_equity": ["HDFCBANK:EQ"], "mcx_gold": []}
    env = IndianMultiAssetEnvironment(cfg)
    assert env.allowed_instruments == {"nse_equity": {"HDFCBANK:EQ"}, "mcx_gold": set()}
    out = validate_orders(_order("nse_equity", "HDFCBANK:EQ"), env.allowed_instruments)
    assert out[0].status == "VALIDATED"
    out = validate_orders(_order("nse_equity", "RELIANCE:EQ"), env.allowed_instruments)
    assert out[0].status == STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE


def test_h_outside_universe_changes_nothing(fresh_env):
    before_cash = fresh_env.portfolio.cash
    before_pos = fresh_env.snapshot_positions()
    before_costs = fresh_env.portfolio.cumulative_transaction_costs
    _, info, _, _ = fresh_env.step(_order("nse_equity", "HDFCBANK:EQ", 5.0))
    ex = info["executions"][0]
    assert ex["execution_status"] == STATUS_NOOP_INSTRUMENT_OUTSIDE_UNIVERSE
    assert ex["executed_quantity"] == 0.0
    assert ex["transaction_cost"] == 0.0
    assert fresh_env.portfolio.cash == before_cash
    assert fresh_env.snapshot_positions() == before_pos
    assert fresh_env.portfolio.cumulative_transaction_costs == before_costs
    assert info["step_pnl"] == 0.0
    fresh_env.reset()


def test_i_fingerprint_and_spec_reflect_universe():
    a = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    cfg = dict(SMALL_CONFIG)
    cfg["universe"] = {"nse_equity": ["RELIANCE:EQ"], "mcx_gold": ["GOLDAUG2023"]}
    b = IndianMultiAssetEnvironment(cfg)
    assert a.fingerprint() != b.fingerprint()
    assert b.spec()["equity_universe"] == ["RELIANCE:EQ"]
    c = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    assert a.fingerprint() == c.fingerprint()


def test_j_no_universe_arg_preserves_legacy_behavior():
    out = validate_orders(_order("nse_equity", "HDFCBANK:EQ"))
    assert out[0].status == "VALIDATED"
