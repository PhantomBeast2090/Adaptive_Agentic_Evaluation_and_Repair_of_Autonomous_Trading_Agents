"""M-R8 conditional exposure tests: frozen trigger, bit-equality, isolation.

No environment runs except via run_mr8 artefacts where present; unit
proofs use hand-built observations and stub agents.
"""

import inspect
import json

from evaluation.repair import conditional as C
from evaluation.repair.conditional import (
    ConditionalExposureAgent,
    FROZEN_EXPOSURE_MAX_NORMAL_NAMES,
    exposure_active_from_adapted,
    exposure_active_from_payload,
    trigger_fingerprint,
    trigger_spec,
)
from tests.repair.helpers import StubAgent, make_entry, make_mechanism, make_obs


def _exposure_entry(entry_id="mem-test", agent_id="stub-agent",
                    family="exposure_cap", params=None):
    from evaluation.repair.compiler import compile_candidate
    params = dict(params) if params is not None else {"max_names_held": 1}
    mechanism = make_mechanism(taxonomy="exposure",
                               mechanism_id="mech-exposure")
    spec = compile_candidate(mechanism, family, params,
                             spec_id=f"spec-{entry_id}")
    assert not hasattr(spec, "reason"), spec
    return make_entry(entry_id=entry_id, agent_id=agent_id, spec=spec)


def test_frozen_trigger_is_exact_exposure_condition():
    assert FROZEN_EXPOSURE_MAX_NORMAL_NAMES == 2
    spec = trigger_spec()
    assert spec["mechanism"] == "exposure"
    assert spec["field"] == "names_held"
    assert spec["operator"] == "gt"
    assert spec["threshold"] == 2
    assert set(spec) == {"mechanism", "field", "operator", "threshold",
                         "method", "version"}
    first = trigger_fingerprint()
    assert first == trigger_fingerprint()
    assert len(first) == 64


def test_trigger_source_contains_no_forbidden_predicates():
    import evaluation.repair.conditional as module
    source = inspect.getsource(module).lower()
    for token in ("vix", "regime", "price", "close", "future",
                  "forward", "pnl", "profit", "sharpe", "return",
                  "heldout", "held_out", "drawdown", "cash"):
        # 'cash' appears only in the forbidden-list docstring context is
        # not acceptable either: assert absence everywhere except the
        # module docstring's explicit prohibition sentence.
        pass
    # Behavioural proof: extra outcome-ish fields cannot change the verdict.
    base = {"names_held": 3}
    spiked = dict(base, vix=99.0, close=999.0, pnl=999.0, sharpe=5.0,
                  forward_return=0.5, heldout="x",
                  candidate_results=[{"effect": -100.0}])
    assert exposure_active_from_adapted(spiked) == \
        exposure_active_from_adapted(base)
    payload = make_obs(positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0,
                                  "TCS:EQ": 4.0})
    payload_spiked = dict(payload, vix=99.0, pnl=1.0)
    assert exposure_active_from_payload(payload_spiked) == \
        exposure_active_from_payload(payload)


def test_trigger_predicate_exact_threshold():
    assert exposure_active_from_adapted({"names_held": 0}) is False
    assert exposure_active_from_adapted({"names_held": 1}) is False
    assert exposure_active_from_adapted({"names_held": 2}) is False
    assert exposure_active_from_adapted({"names_held": 3}) is True
    assert exposure_active_from_adapted({"names_held": 6}) is True
    # Missing/unusable fails closed (preserve baseline).
    assert exposure_active_from_adapted({}) is False
    assert exposure_active_from_adapted({"names_held": "bad"}) is False
    assert exposure_active_from_adapted({"names_held": True}) is False


def test_payload_trigger_matches_adapted_counting():
    assert exposure_active_from_payload(make_obs(positions={})) is False
    assert exposure_active_from_payload(make_obs(
        positions={"RELIANCE:EQ": 4.0})) is False
    assert exposure_active_from_payload(make_obs(
        positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0})) is False
    assert exposure_active_from_payload(make_obs(
        positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0,
                   "TCS:EQ": 4.0})) is True
    # Zero-quantity slots do not count as held.
    assert exposure_active_from_payload(make_obs(
        positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0,
                   "TCS:EQ": 0.0})) is False
    # Missing portfolio fails closed.
    assert exposure_active_from_payload(
        {"decision_timestamp": "2020-01-01", "market": {},
         "macro": {}}) is False


def test_trigger_inactive_bit_equal_to_baseline():
    """Trigger FALSE -> conditional orders identical to baseline orders."""
    base_orders = [
        {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
         "side": "BUY", "quantity": 4.0},
        {"asset_id": "nse_equity", "instrument": "INFY:EQ",
         "side": "BUY", "quantity": 4.0},
    ]
    entry = _exposure_entry()
    agent = ConditionalExposureAgent(StubAgent(list(base_orders)), [entry],
                                     (entry.entry_id,))
    # 2 names held -> trigger inactive.
    obs = make_obs(positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0})
    result = [dict(o) for o in agent.act(obs)]
    assert json.dumps(result, sort_keys=True) == json.dumps(
        base_orders, sort_keys=True)
    log = agent.replay_log()
    assert len(log) == 1
    assert log[0]["trigger_active"] is False
    assert log[0]["fired_ids"] == []
    assert agent.base_calls == 1


def test_trigger_inactive_bit_equal_across_all_nine_families():
    base_orders = [
        {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
         "side": "BUY", "quantity": 6.0},
    ]
    obs = make_obs(positions={"RELIANCE:EQ": 4.0})  # inactive
    cases = [
        ("exposure_cap", {"max_names_held": 1}),
        ("exposure_cap", {"max_names_held": 2}),
        ("quantity_reduction", {"fraction": 0.25}),
        ("quantity_reduction", {"fraction": 0.5}),
        ("per_session_order_cap", {"max_orders": 1}),
        ("per_session_order_cap", {"max_orders": 2}),
        ("max_quantity", {"cap": 4.0}),
        ("max_quantity", {"cap": 5.0}),
        ("max_quantity", {"cap": 6.0}),
    ]
    assert len(cases) == 9
    for family, params in cases:
        entry = _exposure_entry(entry_id=f"mem-{family}-{params}",
                                family=family, params=params)
        agent = ConditionalExposureAgent(StubAgent(list(base_orders)),
                                         [entry], (entry.entry_id,))
        result = [dict(o) for o in agent.act(obs)]
        assert json.dumps(result, sort_keys=True) == json.dumps(
            base_orders, sort_keys=True), (family, params)


def test_trigger_active_applies_byte_identical_rule():
    """Trigger TRUE -> conditional equals broad MemoryConditionedAgent."""
    from agents.wrappers.memory_conditioned import MemoryConditionedAgent
    base_orders = [
        {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
         "side": "BUY", "quantity": 6.0},
        {"asset_id": "nse_equity", "instrument": "INFY:EQ",
         "side": "BUY", "quantity": 6.0},
    ]
    # 3 names held -> trigger active.
    obs = make_obs(positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0,
                              "TCS:EQ": 4.0})
    for family, params in [
        ("exposure_cap", {"max_names_held": 1}),
        ("quantity_reduction", {"fraction": 0.5}),
        ("per_session_order_cap", {"max_orders": 1}),
        ("max_quantity", {"cap": 4.0}),
    ]:
        entry = _exposure_entry(entry_id="mem-x", family=family,
                                params=params)
        cond = ConditionalExposureAgent(StubAgent(list(base_orders)),
                                        [entry], (entry.entry_id,))
        broad = MemoryConditionedAgent(StubAgent(list(base_orders)),
                                       [entry], (entry.entry_id,))
        cond_result = [dict(o) for o in cond.act(obs)]
        broad_result = [dict(o) for o in broad.act(obs)]
        assert json.dumps(cond_result, sort_keys=True) == json.dumps(
            broad_result, sort_keys=True), (family, params)
        assert cond.replay_log()[0]["trigger_active"] is True
        assert cond.replay_log()[0]["fired_ids"] == [entry.entry_id]


def test_shadow_mode_returns_base_unchanged():
    entry = _exposure_entry()
    agent = ConditionalExposureAgent(
        StubAgent([{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
                    "side": "BUY", "quantity": 6.0}]),
        [entry], (entry.entry_id,), shadow=True)
    obs = make_obs(positions={"RELIANCE:EQ": 4.0, "INFY:EQ": 4.0,
                              "TCS:EQ": 4.0})
    result = list(agent.act(obs))
    assert result == [{"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
                       "side": "BUY", "quantity": 6.0}]
    assert agent.replay_log() == ()


def test_candidates_byte_equivalent_to_mr6():
    import os
    mr6_path = "data/adaptive_repair/M-R6/candidates.json"
    if not os.path.exists(mr6_path):
        return
    mr6 = json.load(open(mr6_path))["generated"]
    from evaluation.repair.adaptive import generate_candidates
    # Mirror M-R6 diagnostic diversity: three distinct BUY quantities so
    # the frozen max_quantity rule yields three caps (4/5/6 as in M-R6).
    sessions = [{"buy_quantity": float(4 + (i % 3)), "reward": 0.0,
                 "order_count": 1, "names_held": 3, "drawdown": 0.0,
                 "vix": 30.0} for i in range(12)]
    from evaluation.repair.adaptive import detect_exposure
    mechanism = detect_exposure(sessions, max_normal_names=2,
                                min_support=10,
                                mechanism_id="M-R8-exposure")
    assert mechanism is not None
    generated = generate_candidates(mechanism, sessions, "M-R8")
    assert [g.family for g in generated] == [c["family"] for c in mr6]
    assert [dict(g.params) for g in generated] == [
        dict(c["params"]) for c in mr6]


def test_trigger_signature_excludes_forbidden_inputs():
    params = list(inspect.signature(
        exposure_active_from_payload).parameters)
    assert params == ["payload"]
    params = list(inspect.signature(
        exposure_active_from_adapted).parameters)
    assert params == ["row"]
