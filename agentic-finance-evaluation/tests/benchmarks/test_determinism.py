"""Determinism and identity contracts for canonical benchmarks.

Same observation implies same action; reset restores state; benchmark
fingerprints are stable across fresh instances. Fingerprint values are
pinned in benchmarks/manifest.yaml; these tests assert stability and
cross-instance identity, not the literal digest (the manifest owns it).
"""

from benchmarks.buy_once import BuyOnceBenchmark
from benchmarks.hold import HoldBenchmark
from benchmarks.volatility_threshold import VolatilityThresholdBenchmark
from evaluation.diagnostics.repair.application import fingerprint_agent

from .fixtures import make_obs


def test_hold_never_trades_and_resets():
    agent = HoldBenchmark()
    assert agent.identity.agent_id == "hold-benchmark"
    assert agent.identity.version == "1.0"
    assert agent.act(make_obs(vix=12.5)) == []
    assert agent.act(make_obs(vix=99.0)) == []
    assert agent.reset() is None


def test_buy_once_single_trade_then_hold_and_reset():
    agent = BuyOnceBenchmark()
    assert agent.identity.agent_id == "buy-once-benchmark"
    first = agent.act(make_obs(vix=12.5))
    assert first == [
        {
            "asset_id": "nse_equity",
            "instrument": "RELIANCE:EQ",
            "side": "BUY",
            "quantity": 10.0,
        }
    ]
    assert agent.act(make_obs(vix=12.5)) == []
    agent.reset()
    assert agent.calls == 0
    assert agent.act(make_obs(vix=12.5)) == first


def test_fingerprints_stable_across_instances():
    for cls in (HoldBenchmark, BuyOnceBenchmark, VolatilityThresholdBenchmark):
        first = fingerprint_agent(cls(), cls.identity)
        second = fingerprint_agent(cls(), cls.identity)
        assert first == second
        assert len(first) == 64


def test_manifest_fingerprints_match_live_identities():
    import pathlib

    import yaml

    manifest_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "benchmarks"
        / "manifest.yaml"
    )
    with open(manifest_path) as handle:
        manifest = yaml.safe_load(handle)
    by_id = {row["agent_id"]: row for row in manifest["benchmarks"]}
    for cls in (HoldBenchmark, BuyOnceBenchmark, VolatilityThresholdBenchmark):
        agent = cls()
        row = by_id[agent.identity.agent_id]
        assert row["version"] == agent.identity.version
        assert row["fingerprint"] == fingerprint_agent(agent, agent.identity)
