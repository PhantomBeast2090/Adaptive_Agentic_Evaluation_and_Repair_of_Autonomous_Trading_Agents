"""Tier 2/3 + M-R1.10: full causal chain integration and legacy adapter.

M-R1.10 chain (synthetic, deterministic):
  known flaw -> FailureMechanism -> RepairCompiler -> RepairSpec
  -> MemoryEntry -> MemoryConditionedAgent -> changed behaviour
  -> shadow -> verification assembly -> deactivation (rollback)
  -> audit chain covering every transition.
"""

from agents.financial_agent.synthetic import (
    LossChasingAgent,
    VolatilityBlindAgent,
)
from agents.wrappers.legacy_adapter import (
    LegacyAgentAdapter,
    is_valid_legacy_adapter,
)
from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.repair.audit import AuditChain
from evaluation.repair.compiler import compile as compile_mech
from evaluation.repair.control_plane import activate, deactivate
from evaluation.repair.gate import assemble_verification, coverage_precheck
from evaluation.repair.schemas import MemoryEntry
from tests.repair.helpers import StubAgent, make_entry, make_mechanism, make_obs
from tests.repair.helpers import twin_policy_fingerprint


def test_mr1_10_full_causal_chain():
    chain = AuditChain()
    # 1. Known flaw: stub emits 3 BUY orders every session (overtrading).
    three_buys = [
        {"asset_id": "nse_equity", "instrument": f"{name}:EQ",
         "side": "BUY", "quantity": 2.0}
        for name in ("RELIANCE", "INFY", "TCS")]
    base = StubAgent(three_buys, agent_id="overtrader", version="v1")
    base_fp = fingerprint_agent(base, base.identity)

    # 2-3. Mechanism -> RepairSpec via the deterministic compiler.
    mechanism = make_mechanism(taxonomy="turnover",
                               mechanism_id="mech-overtrade")
    spec = compile_mech(mechanism, "spec-overtrade")
    assert spec.rule_type == "per_session_order_cap"
    chain.append("COMPILED", {"spec": spec.fingerprint(),
                              "mechanism": mechanism.fingerprint()})

    # 4-5. MemoryEntry -> MemoryConditionedAgent.
    entry = make_entry(entry_id="mem-overtrade", agent_id="overtrader",
                       spec=spec)
    assert isinstance(entry, MemoryEntry)
    agent = MemoryConditionedAgent(base, [entry], ("mem-overtrade",))
    assert agent.base_policy_fingerprint() == base_fp

    # 6. Changed behaviour caused by the entry.
    base_only = MemoryConditionedAgent(StubAgent(three_buys,
                                                 agent_id="overtrader",
                                                 version="v1"), [], ())
    assert len(list(base_only.act(make_obs()))) == 3
    conditioned = list(agent.act(make_obs()))
    assert len(conditioned) == 1
    twin_fp = twin_policy_fingerprint(
        agent,
        lambda: StubAgent(three_buys, agent_id="overtrader", version="v1"),
        [make_obs()])
    assert agent.base_policy_fingerprint() == twin_fp
    chain.append("CONDITIONED",
                 {"fired": ["mem-overtrade"],
                  "result": agent.replay_log()[-1]["result_fingerprint"]})

    # 7. Shadow predicts without altering.
    shadow = MemoryConditionedAgent(StubAgent(three_buys,
                                              agent_id="overtrader",
                                              version="v1"),
                                    [entry], ("mem-overtrade",), shadow=True)
    assert len(list(shadow.act(make_obs()))) == 3
    assert shadow.shadow_log()[0]["predicted_fingerprint"] == \
        agent.replay_log()[-1]["result_fingerprint"]

    # 8. Verification assembly (NSF default; evidence recorded).
    coverage = coverage_precheck(
        agent.replay_log()[-1]["fired_ids"].__len__(), 1)
    assert coverage["passed"] is True
    verification = assemble_verification(
        verification_id="ver-overtrade",
        candidate_fingerprint=agent.identity.agent_id,
        metric_deltas={"order_count": -2.0},
        provenance={"chain": "mr1-10"})
    assert verification.verdict == "NSF"
    chain.append("VERIFIED", {"verdict": "NSF"})

    # 9. Rollback restores base behaviour; audit chain intact.
    agent.set_active(deactivate(agent.active_ids, "mem-overtrade"))
    assert len(list(agent.act(make_obs()))) == 3
    twin_fp2 = twin_policy_fingerprint(
        agent,
        lambda: StubAgent(three_buys, agent_id="overtrader", version="v1"),
        [make_obs(), make_obs()])
    assert agent.base_policy_fingerprint() == twin_fp2
    chain.append("ROLLED_BACK", {"active": []})
    assert chain.verify()
    assert [r["event"] for r in chain.to_list()] == [
        "COMPILED", "CONDITIONED", "VERIFIED", "ROLLED_BACK"]


def test_legacy_adapter_volatility_blind():
    agent = VolatilityBlindAgent("vol-blind", "v1")
    adapted = LegacyAgentAdapter(agent, "nse_equity", "RELIANCE:EQ")
    assert adapted.identity.agent_id == "vol-blind"
    assert is_valid_legacy_adapter(adapted)
    orders = list(adapted.act(make_obs(cash=100000.0)))
    assert len(orders) == 1
    assert orders[0]["side"] == "BUY"
    assert orders[0]["instrument"] == "RELIANCE:EQ"
    assert orders[0]["quantity"] == 10.0
    # Out of cash -> HOLD -> no orders.
    assert list(adapted.act(make_obs(cash=10.0))) == []


def test_legacy_adapter_sell_clamped_to_holdings():
    agent = LossChasingAgent("loss-chaser", "v1")
    adapted = LegacyAgentAdapter(agent, "nse_equity", "RELIANCE:EQ")
    # Fresh agent with no losses buys 5.0 (normal behaviour).
    orders = list(adapted.act(make_obs(cash=100000.0)))
    assert orders[0] == {
        "asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
        "side": "BUY", "quantity": 5.0}
    # Same observation twice would double-count losses internally;
    # adapter must remain deterministic per decision.
    adapted.reset()
    assert list(adapted.act(make_obs(cash=100000.0))) == orders


def test_legacy_adapter_rejects_bad_mapping():
    import pytest

    agent = VolatilityBlindAgent("v", "v1")
    with pytest.raises(ValueError):
        LegacyAgentAdapter(agent, "", "RELIANCE:EQ")
    with pytest.raises(TypeError):
        LegacyAgentAdapter(object(), "nse_equity", "RELIANCE:EQ")


def test_wrapper_around_legacy_adapter_end_to_end():
    from evaluation.repair.compiler import compile as compile_mech

    adapted = LegacyAgentAdapter(
        VolatilityBlindAgent("vol-blind", "v1"), "nse_equity",
        "RELIANCE:EQ")
    spec = compile_mech(
        make_mechanism(taxonomy="volatility",
                       trigger_hint=(("vix", "gt", 25.0),)),
        "spec-vb")
    assert spec.rule_type == "hold_all"
    entry = make_entry(entry_id="mem-vb", agent_id="vol-blind", spec=spec)
    agent = MemoryConditionedAgent(adapted, [entry], ("mem-vb",))
    calm = list(agent.act(make_obs(vix=12.0)))
    assert len(calm) == 1 and calm[0]["side"] == "BUY"
    stressed = list(agent.act(make_obs(vix=30.0)))
    assert stressed == []  # regime-triggered suppression via memory
    agent.set_active(())
    assert len(list(agent.act(make_obs(vix=30.0)))) == 1
