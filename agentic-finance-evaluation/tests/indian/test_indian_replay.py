"""L. Deterministic replay tests."""

from environment.indian.environment import IndianMultiAssetEnvironment
from tests.indian.conftest import SMALL_CONFIG

ORDERS = [
    [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
      "side": "BUY", "quantity": 10.0}],
    [{"asset_id": "nse_equity", "instrument": "TCS:EQ",
      "side": "BUY", "quantity": 5.0}],
    [],
    [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
      "side": "SELL", "quantity": 3.0}],
]


def _run(env):
    env.reset()
    trace = []
    done = False
    i = 0
    while not done:
        state, info, done, meta = env.step(ORDERS[i % len(ORDERS)])
        trace.append((state["decision_timestamp"],
                      round(info["portfolio_value"], 6),
                      round(info["step_pnl"], 6),
                      [(e["instrument"], e["executed_quantity"],
                        e["execution_status"]) for e in info["executions"]]))
        i += 1
    return trace


def test_repeated_runs_are_identical():
    t1 = _run(IndianMultiAssetEnvironment(dict(SMALL_CONFIG)))
    t2 = _run(IndianMultiAssetEnvironment(dict(SMALL_CONFIG)))
    assert t1 == t2
    assert len(t1) > 5


def test_fingerprint_stable_and_config_sensitive():
    a = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    b = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    assert a.fingerprint() == b.fingerprint()
    assert a.spec()["market_fingerprint"] == b.spec()["market_fingerprint"]
    other = dict(SMALL_CONFIG)
    other["transaction_cost_bps"] = 10.0
    # Costs enter fills, so the fingerprint binds them too.
    assert IndianMultiAssetEnvironment(other).fingerprint() != a.fingerprint()
    # grid change alters the fingerprint
    other2 = dict(SMALL_CONFIG)
    other2["end_date"] = "2023-05-19"
    assert IndianMultiAssetEnvironment(other2).fingerprint() != a.fingerprint()


def test_spec_reconstructs_episode():
    env = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    spec = env.spec()
    assert spec["grid_sessions"] == len(env.grid)
    assert spec["initial_cash"] == 100000.0
    assert spec["strict_pit"] is True
    clone = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    assert _run(env) == _run(clone)
