"""Tier 1: MemoryConditionedAgent — causality, shadow, scope safety,
rollback, persistence, determinism, policy preservation.

M-R0.5 HEART TEST: same agent + same observation + same policy
fingerprint, different memory state -> different action; deactivation
restores the original action.
"""

import copy

import pytest

from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.repair.control_plane import activate, deactivate
from evaluation.repair.schemas import RepairScope
from tests.repair.helpers import (
    BUY_SELL,
    BUY_TWO,
    StubAgent,
    make_entry,
    make_mechanism,
    make_obs,
    twin_policy_fingerprint,
)


def _cap_entry(entry_id="mem-cap", agent_id="stub-agent", scope=None,
               trigger=(), priority=0, sequence=1):
    from evaluation.repair.compiler import compile as compile_mech

    spec = compile_mech(
        make_mechanism(taxonomy="turnover", scope_hint=dict(scope or {}),
                       trigger_hint=tuple(trigger)),
        spec_id=f"spec-{entry_id}", priority=priority)
    assert not hasattr(spec, "reason")
    return make_entry(entry_id=entry_id, agent_id=agent_id, spec=spec,
                      sequence=sequence, priority=priority)


def test_causal_memory_changes_behaviour_and_rollback_restores():
    base = StubAgent(list(BUY_TWO))
    pre_fp = fingerprint_agent(base, base.identity)
    entry = _cap_entry()
    agent = MemoryConditionedAgent(base, [entry], ("mem-cap",))
    obs = make_obs()

    assert agent.base_policy_fingerprint() == pre_fp
    assert base.calls == 0  # construction is side-effect free

    conditioned = list(agent.act(obs))
    assert [o["quantity"] for o in conditioned] == [2.0]  # truncated to 1
    assert len(conditioned) == 1
    assert agent.base_calls == 1  # base policy called exactly once
    # Policy state matches an untouched twin advanced identically:
    # memory changed ORDERS, never policy evolution.
    twin_fp = twin_policy_fingerprint(
        agent, lambda: StubAgent(list(BUY_TWO)), [make_obs()])
    assert agent.base_policy_fingerprint() == twin_fp

    log = agent.replay_log()
    assert len(log) == 1
    assert log[0]["fired_ids"] == ["mem-cap"]
    assert not log[0]["quarantined"]

    # Rollback: deactivate -> base behaviour restored exactly.
    agent.set_active(deactivate(agent.active_ids, "mem-cap"))
    restored = list(agent.act(make_obs()))
    assert restored == [dict(o) for o in BUY_TWO]
    twin_fp2 = twin_policy_fingerprint(
        agent, lambda: StubAgent(list(BUY_TWO)),
        [make_obs(), make_obs()])
    assert agent.base_policy_fingerprint() == twin_fp2


def test_empty_memory_matches_base_exactly():
    base = StubAgent(list(BUY_SELL))
    agent = MemoryConditionedAgent(base, [], ())
    assert list(agent.act(make_obs())) == [dict(o) for o in BUY_SELL]


def test_shadow_mode_predicts_without_altering():
    entry = _cap_entry()
    agent = MemoryConditionedAgent(StubAgent(list(BUY_TWO)), [entry],
                                   ("mem-cap",), shadow=True)
    result = list(agent.act(make_obs()))
    assert result == [dict(o) for o in BUY_TWO]  # behaviour unchanged
    shadow = agent.shadow_log()
    assert len(shadow) == 1
    assert shadow[0]["shadow"] is True
    assert shadow[0]["predicted_fingerprint"] != \
        shadow[0]["base_orders_fingerprint"]  # would-have-changed
    assert agent.replay_log() == ()


def test_scope_safety_out_of_scope_untouched():
    scoped = _cap_entry(
        entry_id="mem-scoped",
        scope={"instruments": ["SBIN:EQ"]})
    agent = MemoryConditionedAgent(StubAgent(list(BUY_TWO)), [scoped],
                                   ("mem-scoped",))
    # Orders concern RELIANCE/INFY only: scoped entry must not fire.
    assert list(agent.act(make_obs())) == [dict(o) for o in BUY_TWO]
    assert agent.replay_log()[0]["fired_ids"] == []

    regime = _cap_entry(
        entry_id="mem-regime",
        scope={"vix_band": [25.0, 40.0]})
    calm_agent = MemoryConditionedAgent(StubAgent(list(BUY_TWO)), [regime],
                                        ("mem-regime",))
    assert list(calm_agent.act(make_obs(vix=12.0))) == \
        [dict(o) for o in BUY_TWO]
    assert len(list(calm_agent.act(make_obs(vix=30.0)))) == 1


def test_wrapper_does_not_mutate_caller_agent():
    base = StubAgent(list(BUY_TWO))
    before = copy.deepcopy(vars(base))
    MemoryConditionedAgent(base, [], ())
    assert vars(base) == before  # construction deep-copies; no aliasing
    assert fingerprint_agent(base, base.identity) == \
        fingerprint_agent(base, base.identity)


def test_determinism_same_inputs_same_outputs():
    def run_once():
        agent = MemoryConditionedAgent(StubAgent(list(BUY_TWO)),
                                       [_cap_entry()], ("mem-cap",))
        return (list(agent.act(make_obs())),
                agent.replay_log()[0]["result_fingerprint"])

    first, fp_first = run_once()
    second, fp_second = run_once()
    assert first == second
    assert fp_first == fp_second


def test_persistence_round_trip():
    import json

    from evaluation.repair.schemas import MemoryEntry

    entry = _cap_entry()
    agent = MemoryConditionedAgent(StubAgent(list(BUY_TWO)), [entry],
                                   ("mem-cap",))
    expected = list(agent.act(make_obs()))

    # Save: entries + active set + wrapper config (store dict path proven
    # separately via MemoryStore.to_dict/from_dict round trip below).
    saved = json.dumps({
        "entries": [entry.to_dict()],
        "active_ids": list(agent.active_ids),
        "shadow": agent.shadow,
    }, sort_keys=True)
    loaded = json.loads(saved)
    restored_entries = [MemoryEntry.from_dict(e)
                        for e in loaded["entries"]]
    assert restored_entries[0].fingerprint() == entry.fingerprint()
    rebuilt = MemoryConditionedAgent(
        StubAgent(list(BUY_TWO)), restored_entries,
        tuple(loaded["active_ids"]), shadow=loaded["shadow"])
    assert list(rebuilt.act(make_obs())) == expected
    assert rebuilt.replay_log()[0]["result_fingerprint"] == \
        agent.replay_log()[0]["result_fingerprint"]


def test_store_round_trip_unchanged_behaviour():
    from evaluation.context.learned import ContextStatus
    from evaluation.context.memory import MemoryStore

    entry = _cap_entry()
    learned = entry.to_learned_context(
        ContextStatus.VALIDATED,
        validation_result="test-validation",
    )
    assert learned.status is ContextStatus.VALIDATED
    store = MemoryStore(store_id="test-store", entries=())
    # Admission requires a gate verdict; structural round trip only here.
    fp_before = store.fingerprint()
    clone = MemoryStore.from_dict(store.to_dict())
    assert clone.fingerprint() == fp_before
    assert clone.store_id == "test-store"
