"""J. Leakage-boundary tests.

Proves the evaluator-only/oracle separation:

* ``OraclePacket`` can never become a ``TargetObservation``;
* oracle-only fields cannot appear in target observations (closed schema);
* the invocation path accepts only ``TargetObservation``;
* arbitrary mappings are never silently trusted;
* the existing environment's PIT semantics remain the source of target
  observations (a real ``IndianMultiAssetEnvironment.reset()`` output
  wraps cleanly and carries only PIT-gated content).
"""

import pytest

from evaluation.contracts.agent import AgentIdentity, invoke_act
from evaluation.contracts.oracle import OraclePacket, TargetObservation


class StubAgent:
    identity = AgentIdentity("stub-agent", "0.1")

    def reset(self):
        return None

    def act(self, observation):
        return []


def _oracle():
    return OraclePacket(
        packet_id="O-001",
        source="future_bar_close",
        as_of="2023-05-16",
        content={"nse_equity:RELIANCE:EQ": {"future_close": 2500.0}},
        label="t+1 close, evaluator eyes only",
    )


def test_oracle_packet_cannot_become_target_observation():
    with pytest.raises(TypeError):
        TargetObservation.from_environment_state(_oracle())
    oracle = _oracle()
    assert not isinstance(oracle, TargetObservation)
    # No conversion method exists on the packet, by design.
    assert not hasattr(oracle, "to_target_observation")
    assert oracle.evaluator_only is True
    with pytest.raises(ValueError):
        OraclePacket(
            packet_id="O-2",
            source="x",
            as_of="2023-05-16",
            content={},
            evaluator_only=False,
        )


def test_oracle_content_is_immutable():
    oracle = _oracle()
    with pytest.raises(TypeError):
        oracle.content["nse_equity:RELIANCE:EQ"]["future_close"] = 1.0


def test_oracle_only_fields_rejected_from_target_observations():
    forged = {"decision_timestamp": "2023-05-15", "future_close": 2500.0}
    with pytest.raises(TypeError):
        TargetObservation.from_environment_state(forged)


def test_invocation_path_accepts_only_target_observation():
    from tests.indian.conftest import SMALL_CONFIG
    from environment.indian.environment import IndianMultiAssetEnvironment

    env = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    env.reset()
    state = env._state_at(env.grid[0])
    observation = TargetObservation.from_environment_state(state)
    assert invoke_act(StubAgent(), observation) == []
    with pytest.raises(TypeError):
        invoke_act(StubAgent(), state.to_dict())
    with pytest.raises(TypeError):
        invoke_act(StubAgent(), _oracle())
    with pytest.raises(TypeError):
        invoke_act(StubAgent(), None)


def test_no_public_constructor_for_arbitrary_mappings():
    with pytest.raises(TypeError):
        TargetObservation({"decision_timestamp": "2023-05-15"})
    from environment.indian.state import EnvironmentState, PortfolioView
    state = EnvironmentState(
        decision_timestamp="2023-05-15",
        portfolio=PortfolioView(
            cash=100000.0, positions={}, holdings_value=0.0,
            total_equity=100000.0, exposure=0.0, realized_pnl=0.0,
            unrealized_pnl=0.0, cumulative_costs=0.0,
        ),
    )
    # from_environment_state is idempotent on trusted observations.
    observation = TargetObservation.from_environment_state(state)
    assert TargetObservation.from_environment_state(observation) is observation


def test_environment_pit_output_is_the_source_of_observations():
    from tests.indian.conftest import SMALL_CONFIG
    from environment.indian.environment import IndianMultiAssetEnvironment

    env = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    env.reset()
    state = env._state_at(env.grid[0])
    state_dict = state.to_dict()
    observation = TargetObservation.from_environment_state(state)
    # Only the five environment blocks; no oracle content by construction.
    assert set(observation.keys()) == {
        "decision_timestamp",
        "market",
        "macro",
        "portfolio",
        "calendar",
    }
    assert observation.decision_timestamp == env.grid[0].isoformat()
    # The agent invocation path works end to end on real PIT output.
    assert invoke_act(StubAgent(), observation) == []
    # Mutating the raw dict afterwards cannot corrupt the snapshot.
    state_dict["portfolio"]["cash"] = -1.0
    assert observation["portfolio"]["cash"] != -1.0
