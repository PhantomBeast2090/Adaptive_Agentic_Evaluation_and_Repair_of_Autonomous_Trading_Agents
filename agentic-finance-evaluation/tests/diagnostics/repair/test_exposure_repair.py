"""Exposure (M2) repair: routing, breadth enforcement, divergence.

The exposure class must route to a genuinely distinct rule
(exposure_cap/max_names_held, validated against gross_exposure_max),
not relabel the turnover order-cap. No market episodes: stub agents
and hand-built observations only.
"""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.application import GuardrailedAgent
from evaluation.diagnostics.repair.provider import DeterministicRuleProvider


def _proposal_kwargs(**overrides):
    params = {
        "repair_id": "repair-D-H-exposure",
        "diagnostic_id": "D",
        "baseline_evaluation_id": "B-R",
        "baseline_fingerprint": "bfp",
        "diagnostic_state_fingerprint": "dfp",
        "target_agent_identity": AgentIdentity("bench", "1.0"),
        "target_agent_fingerprint": "tfp",
        "hypothesis_id": "H-exposure",
        "hypothesis_fingerprint": "hfp",
        "failure_class": "exposure",
        "evidence_refs": ("E-1",),
    }
    params.update(overrides)
    return params


def test_exposure_routes_to_breadth_rule_and_metric():
    proposal = DeterministicRuleProvider().propose(**_proposal_kwargs())
    assert proposal.target_metric == "gross_exposure_max"
    assert proposal.target_direction is ExpectedDirection.DECREASE
    (rule,) = proposal.parameters["rules"]
    assert rule["type"] == "exposure_cap"
    assert rule["max_names_held"] == 1


def test_turnover_routing_unchanged():
    proposal = DeterministicRuleProvider().propose(
        **_proposal_kwargs(failure_class="turnover")
    )
    assert proposal.target_metric == "turnover"
    (rule,) = proposal.parameters["rules"]
    assert rule == {"type": "per_session_order_cap", "max_orders": 1}


class _BreadthStub:
    identity = AgentIdentity("bench", "1.0")

    def __init__(self, orders):
        self._orders = list(orders)

    def reset(self):
        return None

    def act(self, observation):
        return [dict(order) for order in self._orders]


def _obs(positions):
    return {
        "portfolio": {
            "positions": {
                key: {"quantity": quantity, "avg_cost": 100.0}
                for key, quantity in positions.items()
            }
        }
    }


def _buy(name):
    return {
        "asset_id": "nse_equity",
        "instrument": name,
        "side": "BUY",
        "quantity": 1.0,
    }


def _agent(orders):
    return GuardrailedAgent(
        _BreadthStub(orders),
        [{"type": "exposure_cap", "max_names_held": 1}],
        AgentIdentity("bench", "1.0"),
    )


def test_breadth_cap_blocks_new_names_only():
    held_obs = _obs({"nse_equity:RELIANCE:EQ": 4.0})
    agent = _agent([_buy("RELIANCE:EQ"), _buy("TCS:EQ")])
    out = agent.act(held_obs)
    assert [o["instrument"] for o in out] == ["RELIANCE:EQ"]
    flat = _agent([_buy("RELIANCE:EQ"), _buy("TCS:EQ")])
    assert [o["instrument"] for o in flat.act(_obs({}))] == [
        "RELIANCE:EQ"
    ]


def test_breadth_cap_passes_sells_and_invalid_params_refused():
    agent = _agent([{
        "asset_id": "nse_equity",
        "instrument": "TCS:EQ",
        "side": "SELL",
        "quantity": 2.0,
    }])
    assert len(agent.act(_obs({"nse_equity:RELIANCE:EQ": 1.0}))) == 1
    with pytest.raises(ValueError):
        GuardrailedAgent(
            _BreadthStub([]),
            [{"type": "exposure_cap", "max_names_held": 0}],
            AgentIdentity("bench", "1.0"),
        )
    with pytest.raises(ValueError):
        GuardrailedAgent(
            _BreadthStub([]),
            [{"type": "telepathy_cap"}],
            AgentIdentity("bench", "1.0"),
        )


def test_breadth_vs_order_cap_diverge():
    orders = [_buy("RELIANCE:EQ"), _buy("TCS:EQ")]
    breadth = _agent(orders).act(
        _obs({"nse_equity:RELIANCE:EQ": 4.0})
    )
    capped = GuardrailedAgent(
        _BreadthStub(orders),
        [{"type": "per_session_order_cap", "max_orders": 1}],
        AgentIdentity("bench", "1.0"),
    ).act(_obs({"nse_equity:RELIANCE:EQ": 4.0}))
    assert [o["instrument"] for o in breadth] == ["RELIANCE:EQ"]
    assert [o["instrument"] for o in capped] == ["RELIANCE:EQ"]
    # Geometry differs when the held name is ordered second: the order
    # cap keeps the first-listed order regardless of holdings, while
    # the breadth cap keeps held-name orders wherever listed.
    flipped = [_buy("TCS:EQ"), _buy("RELIANCE:EQ")]
    assert [o["instrument"] for o in _agent(flipped).act(
        _obs({"nse_equity:RELIANCE:EQ": 4.0})
    )] == ["RELIANCE:EQ"]
    assert [o["instrument"] for o in GuardrailedAgent(
        _BreadthStub(flipped),
        [{"type": "per_session_order_cap", "max_orders": 1}],
        AgentIdentity("bench", "1.0"),
    ).act(_obs({"nse_equity:RELIANCE:EQ": 4.0}))] == ["TCS:EQ"]
