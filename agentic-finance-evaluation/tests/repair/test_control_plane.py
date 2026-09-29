"""Tier 1: control plane — scope, triggers, conflicts, quarantine,
rollback, and enforcement conformance vs GuardrailedAgent."""

import pytest

from benchmarks.observation import build_order
from evaluation.diagnostics.repair.application import GuardrailedAgent
from evaluation.contracts.agent import AgentIdentity
from evaluation.repair import control_plane
from evaluation.repair.control_plane import (
    activate,
    apply_rule_ops,
    deactivate,
    evaluate_trigger,
    scope_matches,
    select,
)
from evaluation.repair.schemas import RepairScope
from tests.repair.helpers import (
    BUY_SELL,
    BUY_TWO,
    StubAgent,
    make_entry,
    make_mechanism,
    make_obs,
)


def _spec_for(rule_type="per_session_order_cap", params=None, scope=None,
              trigger=(), spec_id="spec-001"):
    from evaluation.repair.schemas import RepairSpec

    return RepairSpec(
        spec_id=spec_id, mechanism_fingerprint="mfp", rule_type=rule_type,
        rule_params=dict(params or {}),
        scope=scope or RepairScope(),
        trigger=tuple(trigger),
    )


def test_scope_matching_axes():
    payload = make_obs(vix=30.0)
    all_scope = RepairScope()
    assert scope_matches(all_scope, "stub-agent", payload, list(BUY_TWO))
    assert not scope_matches(RepairScope(agent_id="other"), "stub-agent",
                             payload, list(BUY_TWO))
    assert scope_matches(
        RepairScope(instruments=("RELIANCE:EQ",)), "stub-agent", payload,
        list(BUY_TWO))
    assert not scope_matches(
        RepairScope(instruments=("SBIN:EQ",)), "stub-agent", payload,
        list(BUY_TWO))
    assert not scope_matches(
        RepairScope(instruments=("SBIN:EQ",)), "stub-agent", payload, [])
    assert scope_matches(
        RepairScope(actions=("SELL",)), "stub-agent", payload,
        list(BUY_SELL))
    assert not scope_matches(
        RepairScope(actions=("SELL",)), "stub-agent", payload,
        [dict(BUY_TWO[0])])
    assert scope_matches(
        RepairScope(vix_band=(25.0, 40.0)), "stub-agent", payload,
        list(BUY_TWO))
    assert not scope_matches(
        RepairScope(vix_band=(25.0, 40.0)), "stub-agent",
        make_obs(vix=12.0), list(BUY_TWO))
    assert scope_matches(
        RepairScope(date_from="2023-05-01", date_to="2023-05-31"),
        "stub-agent", payload, list(BUY_TWO))
    assert not scope_matches(
        RepairScope(date_from="2023-06-01"), "stub-agent", payload,
        list(BUY_TWO))


def test_drawdown_trigger_field():
    from evaluation.repair.control_plane import resolve_trigger_field
    base = {"decision_timestamp": "2023-05-15",
            "portfolio": {"cash": 90000.0, "total_equity": 100000.0,
                          "unrealized_pnl": -8000.0, "positions": {}}}
    assert resolve_trigger_field("drawdown", base, []) == pytest.approx(0.08)
    assert evaluate_trigger((("drawdown", "gt", 0.05),), base, []) is True
    assert evaluate_trigger((("drawdown", "gt", 0.10),), base, []) is False
    flat = {"decision_timestamp": "2023-05-15",
            "portfolio": {"cash": 100000.0, "total_equity": 100000.0,
                          "unrealized_pnl": 0.0, "positions": {}}}
    assert evaluate_trigger((("drawdown", "gt", 0.05),), flat, []) is False
    missing = {"decision_timestamp": "2023-05-15", "portfolio": {}}
    assert evaluate_trigger((("drawdown", "gt", 0.05),), missing, []) is False


def test_trigger_evaluation():
    payload = make_obs(vix=30.0, cash=5000.0)
    assert evaluate_trigger((("vix", "gt", 25.0),), payload, list(BUY_TWO))
    assert not evaluate_trigger((("vix", "gt", 35.0),), payload,
                                list(BUY_TWO))
    assert evaluate_trigger((("buy_present", "eq", True),), payload,
                            list(BUY_TWO))
    assert not evaluate_trigger((("sell_present", "eq", True),), payload,
                                [dict(BUY_TWO[0])])
    assert evaluate_trigger(
        (("vix", "gte", 25.0), ("cash", "lt", 10000.0)), payload,
        list(BUY_TWO))
    assert not evaluate_trigger((("vix", "gt", 25.0),),
                                make_obs(), list(BUY_TWO))
    with pytest.raises(ValueError):
        evaluate_trigger((("nope", "gt", 1),), payload, list(BUY_TWO))


def test_select_single_and_empty():
    entry = make_entry(spec=_spec_for(params={"max_orders": 1}))
    payload = make_obs()
    sel = select([entry], ("mem-001",), "stub-agent", payload,
                 list(BUY_TWO))
    assert not sel.quarantined
    assert [e.entry_id for e in sel.fired] == ["mem-001"]
    sel_empty = select([entry], (), "stub-agent", payload, list(BUY_TWO))
    assert sel_empty.fired == () and not sel_empty.quarantined
    other_agent = make_entry(entry_id="mem-x", agent_id="other",
                             spec=_spec_for(params={"max_orders": 1},
                                            spec_id="s-x"))
    sel_agent = select([other_agent], ("mem-x",), "stub-agent", payload,
                       list(BUY_TWO))
    assert sel_agent.fired == ()


def test_conflict_resolution_specificity_priority_sequence():
    broad = make_entry(
        entry_id="mem-broad", spec=_spec_for(params={"max_orders": 2},
                                            spec_id="s-broad"))
    narrow = make_entry(
        entry_id="mem-narrow",
        spec=_spec_for(params={"max_orders": 1}, spec_id="s-narrow",
                       scope=RepairScope(instruments=("RELIANCE:EQ",))))
    payload = make_obs()
    sel = select([broad, narrow], ("mem-broad", "mem-narrow"),
                 "stub-agent", payload, list(BUY_TWO))
    assert [e.entry_id for e in sel.fired] == ["mem-narrow"]
    low = make_entry(entry_id="mem-low", priority=0,
                     spec=_spec_for(params={"max_orders": 2},
                                    spec_id="s-low"))
    high = make_entry(entry_id="mem-high", priority=5,
                      spec=_spec_for(params={"max_orders": 1},
                                     spec_id="s-high"))
    sel2 = select([low, high], ("mem-low", "mem-high"), "stub-agent",
                  payload, list(BUY_TWO))
    assert [e.entry_id for e in sel2.fired] == ["mem-high"]


def test_full_tie_quarantines_and_applies_neither():
    first = make_entry(
        entry_id="mem-1", spec=_spec_for(params={"max_orders": 1},
                                        spec_id="s-1"))
    second = make_entry(
        entry_id="mem-2", spec=_spec_for(params={"max_orders": 0},
                                        spec_id="s-2"))
    payload = make_obs()
    sel = select([first, second], ("mem-1", "mem-2"), "stub-agent",
                 payload, list(BUY_TWO))
    assert sel.quarantined
    assert sel.fired == ()
    assert "indistinguishable" in sel.quarantine_reason


def test_identical_rules_dedupe_without_quarantine():
    first = make_entry(
        entry_id="mem-1", spec=_spec_for(params={"max_orders": 1},
                                        spec_id="s-1"))
    second = make_entry(
        entry_id="mem-2", spec=_spec_for(params={"max_orders": 1},
                                        spec_id="s-2"))
    sel = select([first, second], ("mem-1", "mem-2"), "stub-agent",
                 make_obs(), list(BUY_TWO))
    assert not sel.quarantined
    assert {e.entry_id for e in sel.fired} == {"mem-1", "mem-2"}


def test_activate_deactivate_are_append_only():
    active: tuple = ()
    active = activate(active, "mem-1")
    active = activate(active, "mem-1")
    assert active == ("mem-1",)
    active = activate(active, "mem-2")
    assert active == ("mem-1", "mem-2")
    rolled = deactivate(active, "mem-1")
    assert rolled == ("mem-2",)
    assert active == ("mem-1", "mem-2")  # input untouched


def test_apply_conformance_vs_guardrailed_agent():
    """apply_rule_ops must match GuardrailedAgent.act exactly."""
    stub = StubAgent(list(BUY_TWO))
    identity = AgentIdentity("stub-agent", "v1+c")
    obs = make_obs(vix=30.0)
    held_obs = make_obs(
        vix=30.0, positions={"RELIANCE:EQ": 2.0, "INFY:EQ": 1.0})
    rule_sets = [
        [{"type": "hold_all"}],
        [{"type": "per_session_order_cap", "max_orders": 1}],
        [{"type": "per_session_order_cap", "max_orders": 0}],
        [{"type": "exposure_cap", "max_names_held": 1}],
        [{"type": "per_session_order_cap", "max_orders": 2},
         {"type": "exposure_cap", "max_names_held": 1}],
        [{"type": "max_quantity", "cap": 1.0}],
        [{"type": "per_session_order_cap", "max_orders": 2},
         {"type": "max_quantity", "cap": 1.0}],
    ]
    for rules in rule_sets:
        for observation in (obs, held_obs):
            expected = list(
                GuardrailedAgent(StubAgent(list(BUY_TWO)), rules,
                                 identity).act(observation))
            got = apply_rule_ops(list(BUY_TWO), rules, observation)
            assert got == expected, rules
    with pytest.raises(ValueError):
        apply_rule_ops(list(BUY_TWO), [{"type": "quantum-throttle"}],
                       obs)
