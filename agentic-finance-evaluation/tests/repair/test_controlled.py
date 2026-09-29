"""Controlled-benchmark tests (M-R2/M-R3): compiler mappings, benchmark
determinism, protocol pre-registration, gate edges, deliverable pins."""

import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from benchmarks.loss_chasing import LossChasingBenchmark
from benchmarks.volatility_blind import VolatilityBlindBenchmark
from evaluation.repair.compiler import Uncompilable, compile as compile_mech
from tests.repair.helpers import make_mechanism

BASE = os.path.join(os.path.dirname(__file__), "..", "..")


def _obs(vix, cash=100000.0):
    from tests.repair.helpers import make_obs

    return make_obs(vix=vix, cash=cash)


def test_volatility_compiles_to_hold_all():
    spec = compile_mech(
        make_mechanism(taxonomy="volatility",
                       trigger_hint=(("vix", "gt", 25.0),)),
        "spec-mr2")
    assert spec.rule_type == "hold_all"
    assert spec.trigger == (("vix", "gt", 25.0),)


def test_loss_chasing_compiles_to_max_quantity():
    spec = compile_mech(
        make_mechanism(taxonomy="loss-chasing",
                       scope_hint={"max_quantity_cap": 5.0}),
        "spec-mr3")
    assert spec.rule_type == "max_quantity"
    assert spec.rule() == {"type": "max_quantity", "cap": 5.0}


def test_provider_loss_chasing_row_coherent():
    from evaluation.diagnostics.repair.provider import RULE_TABLE

    rows = {keyword: (rules, target) for keyword, rules, target, _
            in RULE_TABLE}
    assert rows["loss-chasing"][0] == [{"type": "max_quantity",
                                        "cap": 5.0}]
    assert rows["loss-chasing"][1] == "max_post_loss_quantity"


def test_vol_blind_ignores_vix_and_is_deterministic():
    first, second = VolatilityBlindBenchmark(), VolatilityBlindBenchmark()
    assert first.act(_obs(12.0)) == second.act(_obs(12.0))
    assert first.act(_obs(12.0)) == first.act(_obs(40.0))
    assert first.act(_obs(12.0))[0]["quantity"] == 1.0


def test_loss_chasing_escalates_deterministically():
    def run():
        agent = LossChasingBenchmark()
        agent.reset()
        values = [100000.0, 99000.0, 98000.0, 97000.0, 100000.0]
        quantities = []
        for index, value in enumerate(values):
            obs = _obs(12.0)
            obs["portfolio"]["total_equity"] = value
            orders = agent.act(obs)
            quantities.append(orders[0]["quantity"] if orders else 0.0)
        return quantities

    first, second = run(), run()
    assert first == second
    assert first[0] == 5.0  # normal size before any loss
    assert first[1] == 10.0 and first[2] == 20.0  # doubling escalation
    assert first[4] == 5.0  # recovery resets to normal


def test_memory_wrapper_binds_escalation():
    from evaluation.repair.schemas import MemoryEntry

    spec = compile_mech(
        make_mechanism(taxonomy="loss-chasing",
                       scope_hint={"max_quantity_cap": 5.0}),
        "spec-cap")
    entry = MemoryEntry(
        entry_id="mem-cap", agent_id="loss-chasing-benchmark", spec=spec,
        source_evaluation_id="test",
        diagnostic_evidence=("test:escalation",),
        provenance={"mechanism_fingerprint": "mfp"})
    agent = MemoryConditionedAgent(LossChasingBenchmark(), [entry],
                                   ("mem-cap",))
    values = [100000.0, 99000.0, 98000.0, 97000.0]
    capped = []
    for value in values:
        obs = _obs(12.0)
        obs["portfolio"]["total_equity"] = value
        orders = list(agent.act(obs))
        capped.append(orders[0]["quantity"] if orders else 0.0)
    assert capped == [5.0, 5.0, 5.0, 5.0]
    assert agent.replay_log()[-1]["fired_ids"] == ["mem-cap"]


def test_protocols_preregistered_and_ordered():
    for name in ("mr2", "mr3"):
        with open(os.path.join(
                BASE, "configs", "controlled_repair",
                f"{name}_protocol.yaml")) as handle:
            protocol = yaml.safe_load(handle)
        assert protocol["label"] == "CONTROLLED-KNOWN-MECHANISM"
        diag = protocol["windows"]["diagnostic"]
        held = protocol["windows"]["heldout"]
        assert held["start"] > diag["end"]  # strictly-later held-out
        assert protocol["statistics"]["seed"] == 20260929
        assert "acceptance" in protocol and "tolerances" in protocol["targets"]


def test_gate_nsf_and_coverage_edges():
    from evaluation.repair.gate import assemble_verification, coverage_precheck

    assert coverage_precheck(3, 5)["passed"] is False
    verification = assemble_verification(
        verification_id="v-edge", candidate_fingerprint="c",
        bootstrap_ci={"lower": -1.0, "upper": 2.0},
        provenance={"note": "straddling CI"})
    assert verification.verdict == "NSF"


def test_no_forbidden_machinery_in_controlled_path():
    import ast

    for path in ("benchmarks/volatility_blind.py",
                 "benchmarks/loss_chasing.py",
                 "scripts/run_controlled_repair.py",
                 "agents/wrappers/memory_conditioned.py",
                 "evaluation/repair/control_plane.py",
                 "evaluation/repair/compiler.py"):
        tree = ast.parse(open(os.path.join(BASE, path)).read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        banned = [m for m in imported
                  if "torch" in m or "transformers" in m or "sklearn" in m
                  or "numpy" in m or "embedding" in m]
        assert not banned, (path, banned)
        source = open(os.path.join(BASE, path)).read()
        banned_tokens = ["torch.", "transformers.", "fine_tune", "finetune",
                         ".backward(", "embedding", "faiss", "vector_db",
                         "numpy", "sklearn"]
        hits = [t for t in banned_tokens if t in source]
        assert not hits, (path, hits)


def test_deliverables_pinned():
    import json

    for exp, verdict in (("MR2-20260929", "REJECT"),
                         ("MR3-20260929", "NSF")):
        result = json.load(open(os.path.join(
            BASE, "data", "controlled_repair", exp, "result.json")))
        manifest = json.load(open(os.path.join(
            BASE, "data", "controlled_repair", exp, "manifest.json")))
        assert result["verdict"] == verdict
        assert manifest["verdict"] == verdict
        assert manifest["label"] == "CONTROLLED-KNOWN-MECHANISM"
        assert result["policy_fingerprint"] == \
            manifest["policy_fingerprint"]


def test_mr4a_and_mr4b_deliverables_pinned():
    import json

    result = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4A-20260930", "result.json")))
    assert result["verdict"] == "ACCEPT"
    assert result["support"] == {"diag": 16, "held": 8}
    assert result["persistence"] == "REPRODUCED"
    assert result["rollback"] == "RESTORED"
    assert "store_fingerprint" in result
    result_b = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4B-20260930", "result.json")))
    assert result_b["verdict"] == "REJECT"
    manifest_b = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4B-20260930", "manifest.json")))
    assert manifest_b["label"] == "CONTROLLED-KNOWN-MECHANISM"
    assert manifest_b["verdict"] == "REJECT"
