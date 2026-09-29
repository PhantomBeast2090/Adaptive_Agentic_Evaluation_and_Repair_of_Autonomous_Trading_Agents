"""M-R4A power-benchmark tests: feed determinism, episode table,
escalation structure, pairing, support counting, deliverable pins."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from benchmarks import loss_chasing_power as feed
from benchmarks.loss_chasing import LossChasingBenchmark

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
PROTOCOL = os.path.join(
    BASE, "configs", "controlled_repair", "mr4a_protocol.yaml")


def _protocol():
    with open(PROTOCOL) as handle:
        return yaml.safe_load(handle)


def test_feed_deterministic_and_matches_protocol():
    protocol = _protocol()
    first = feed.generate_closes(8, 100.0)
    second = feed.generate_closes(8, 100.0)
    assert first == second
    assert len(first) == 96
    assert feed.episode_ranges(8, 0) == protocol["episodes"]["diagnostic"]
    assert len(protocol["episodes"]["diagnostic"]) == 16
    assert len(protocol["episodes"]["heldout"]) == 8
    assert feed.UNIT_RETURNS[2] == -0.015  # decline structure pinned


def test_base_generates_episodes_with_resets_and_no_starvation():
    protocol = _protocol()
    feed_spec = protocol["feed"]
    closes = feed.generate_closes(8, feed_spec["start_price"])
    trace = feed.run_segment(LossChasingBenchmark(), closes, 0,
                             feed_spec["initial_cash"])
    excess = [e["excess"] for e in feed.episode_excess(
        trace["sessions"], protocol["episodes"]["diagnostic"],
        feed_spec["normal_quantity"])]
    assert sum(1 for x in excess if x > 0) >= 10
    assert trace["clamped_sessions"] == 0  # cash never binds
    assert feed.inactivity_rate(trace["sessions"]) == 0.0


def test_repaired_excess_zero_and_normal_sessions_equal():
    import copy

    from agents.wrappers.memory_conditioned import MemoryConditionedAgent
    from evaluation.repair.compiler import compile as compile_mech
    from evaluation.repair.schemas import FailureMechanism, MemoryEntry

    protocol = _protocol()
    feed_spec = protocol["feed"]
    closes = feed.generate_closes(8, feed_spec["start_price"])
    mechanism = FailureMechanism(
        mechanism_id="mech-test", taxonomy="loss-chasing",
        condition=("protocol:test",), scope_hint={"max_quantity_cap": 5.0},
        trigger_hint=(), evidence_refs=("feed",),
        provenance={"protocol": "test"})
    spec = compile_mech(mechanism, "spec-test")
    entry = MemoryEntry(
        entry_id="mem-test", agent_id="loss-chasing-benchmark", spec=spec,
        source_evaluation_id="test", diagnostic_evidence=("test",),
        provenance={"mechanism_fingerprint": "mfp"})
    base = feed.run_segment(LossChasingBenchmark(), closes, 0,
                            feed_spec["initial_cash"])
    served = MemoryConditionedAgent(LossChasingBenchmark(), [entry],
                                    ("mem-test",))
    rep = feed.run_segment(served, closes, 0, feed_spec["initial_cash"])
    rep_excess = [e["excess"] for e in feed.episode_excess(
        rep["sessions"], protocol["episodes"]["diagnostic"],
        feed_spec["normal_quantity"])]
    assert all(x == 0.0 for x in rep_excess)
    ep_sessions = {t for ep in protocol["episodes"]["diagnostic"]
                   for t in range(ep[0], ep[1] + 1)}
    for b, r in zip(base["sessions"], rep["sessions"]):
        if b["session"] not in ep_sessions:
            assert b["buy_quantity"] == r["buy_quantity"]
    assert any(b["buy_quantity"] != r["buy_quantity"]
               for b, r in zip(base["sessions"], rep["sessions"])
               if b["session"] in ep_sessions)


def test_paired_statistics_direction():
    from evaluation.repair.gate import coverage_precheck, paired_bootstrap_ci

    diffs = [-40.0, -15.0, -20.0, -10.0, -35.0, -25.0, -30.0, -12.0,
             -18.0, -22.0, -28.0, -16.0, -24.0, -14.0, -32.0, -26.0]
    ci = paired_bootstrap_ci(diffs, seed=20260930, n_boot=1000)
    assert ci["upper"] < 0
    assert ci["mean"] < 0
    assert coverage_precheck(16, 10)["passed"] is True


def test_mr4a_deliverables_pinned():
    import json

    result = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4A-20260930", "result.json")))
    manifest = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4A-20260930", "manifest.json")))
    assert result["verdict"] == "ACCEPT"
    assert manifest["verdict"] == "ACCEPT"
    assert manifest["label"] == "CONTROLLED-KNOWN-MECHANISM"
    assert result["support"] == {"diag": 16, "held": 8}
    assert result["persistence"] == "REPRODUCED"
    assert result["rollback"] == "RESTORED"
    assert result["store_fingerprint"] == manifest.get(
        "store_fingerprint", result["store_fingerprint"])
    audit = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4A-20260930", "audit.json")))
    assert [r["event"] for r in audit] == [
        "FEED_FROZEN", "BASE_SEALED", "DIAGNOSED", "COMPILED", "SHADOWED",
        "CONDITIONED", "GATED", "DECIDED", "ADMITTED", "PERSISTED",
        "ROLLED_BACK"]
