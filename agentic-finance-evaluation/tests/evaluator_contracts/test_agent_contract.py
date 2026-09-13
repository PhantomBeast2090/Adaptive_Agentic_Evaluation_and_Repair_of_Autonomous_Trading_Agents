"""A. Target-agent contract tests."""

import pytest

from evaluation.contracts.agent import (
    AgentIdentity,
    invoke_act,
    is_valid_target_agent,
    validate_target_agent,
)
from evaluation.contracts.oracle import OraclePacket, TargetObservation
from environment.indian.state import EnvironmentState, PortfolioView


def _observation():
    state = EnvironmentState(
        decision_timestamp="2023-05-15",
        portfolio=PortfolioView(
            cash=100000.0,
            positions={},
            holdings_value=0.0,
            total_equity=100000.0,
            exposure=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            cumulative_costs=0.0,
        ),
    )
    return TargetObservation.from_environment_state(state)


class StubAgent:
    def __init__(self):
        self.identity = AgentIdentity("stub-agent", "0.1")
        self.resets = 0

    def reset(self):
        self.resets += 1

    def act(self, observation):
        assert isinstance(observation, TargetObservation)
        return []


def test_valid_agent_accepted():
    assert validate_target_agent(StubAgent()) == []
    assert is_valid_target_agent(StubAgent())


def test_malformed_agents_rejected():
    assert not is_valid_target_agent(None)
    assert not is_valid_target_agent(object())
    assert "act" in " ".join(validate_target_agent(object())).lower()

    class NoAct:
        identity = AgentIdentity("x", "1")

        def reset(self):
            return None

    assert not is_valid_target_agent(NoAct())

    class BadIdentity:
        identity = "not-an-identity"

        def reset(self):
            return None

        def act(self, observation):
            return []

    errors = validate_target_agent(BadIdentity())
    assert any("identity" in e for e in errors)


def test_identity_version_behavior():
    first = AgentIdentity("agent", "1.0")
    second = AgentIdentity("agent", "2.0")
    assert first.fingerprint() != second.fingerprint()
    assert str(first) == "agent@1.0"
    with pytest.raises(ValueError):
        AgentIdentity("", "1.0")
    with pytest.raises(ValueError):
        AgentIdentity("agent", "  ")
    assert AgentIdentity.from_dict(first.to_dict()) == first


def test_reset_semantics_preserved():
    agent = StubAgent()
    agent.reset()
    agent.reset()
    assert agent.resets == 2


def test_optional_adapt_not_required():
    # No adapt method at all: still a valid target agent.
    assert is_valid_target_agent(StubAgent())

    class BadAdapt(StubAgent):
        adapt = "not-callable"

    errors = validate_target_agent(BadAdapt())
    assert any("adapt" in e for e in errors)


def test_no_hidden_reasoning_required_on_invocation():
    # act returns orders only; no rationale/chain-of-thought needed.
    orders = invoke_act(StubAgent(), _observation())
    assert orders == []

    class OrderAgent(StubAgent):
        def act(self, observation):
            return [
                {
                    "asset_id": "nse_equity",
                    "instrument": "RELIANCE:EQ",
                    "side": "BUY",
                    "quantity": 1.0,
                }
            ]

    orders = invoke_act(OrderAgent(), _observation())
    assert orders[0]["side"] == "BUY"

    class BrokenAgent(StubAgent):
        def act(self, observation):
            return "BUY"

    with pytest.raises(TypeError):
        invoke_act(BrokenAgent(), _observation())


def test_oracle_packet_rejected_on_invocation_path():
    oracle = OraclePacket(
        packet_id="O-1",
        source="future_prices",
        as_of="2023-05-16",
        content={"nse_equity:RELIANCE:EQ": 2500.0},
    )
    with pytest.raises(TypeError):
        invoke_act(StubAgent(), oracle)
