"""E1 leakage tests on the evaluation path (not just E0 units).

Proves, through the actual baseline runner and trusted adapter:

* serialized dictionaries cannot become TargetObservation;
* OraclePacket cannot become TargetObservation;
* OraclePacket cannot reach the target agent;
* the agent receives only TargetObservation;
* future/oracle fields cannot enter a target observation;
* actual Indian EnvironmentState becomes TargetObservation via trusted.py.
"""

import pytest

from evaluation.baseline import run_baseline
from evaluation.baseline.trusted import observe_current, split_visibility
from evaluation.contracts.oracle import OraclePacket, TargetObservation
from environment.indian.environment import IndianMultiAssetEnvironment

from .stubs import HoldAgent, RecordingAgent, small_config


def _payload():
    return {
        "decision_timestamp": "2023-05-15",
        "market": {
            "nse_equity:RELIANCE:EQ": {
                "status": "AVAILABLE",
                "venue": "NSE_CM",
                "observation_date": "2023-05-12",
                "availability_date": None,
                "vintage": None,
                "values": {"close": 2484.35},
                "reason": "test",
            }
        },
        "macro": {
            "brent": {
                "status": "INFO_UNAVAILABLE",
                "venue": "EIA",
                "observation_date": None,
                "availability_date": None,
                "vintage": None,
                "values": {},
                "reason": "test",
            }
        },
        "portfolio": {"cash": 100000.0, "total_equity": 100000.0},
        "calendar": {"NSE_CM": "OPEN"},
    }


def _oracle():
    return OraclePacket(
        packet_id="O-E1-1",
        source="future_bar_close",
        as_of="2023-05-16",
        content={"nse_equity:RELIANCE:EQ": {"future_close": 2500.0}},
    )


def test_dictionary_cannot_become_target_observation():
    with pytest.raises(TypeError):
        TargetObservation.from_environment_state(_payload())


def test_oracle_packet_cannot_become_target_observation():
    with pytest.raises(TypeError):
        TargetObservation.from_environment_state(_oracle())


def test_oracle_packet_cannot_reach_target_agent():
    from evaluation.contracts.agent import invoke_act

    agent = RecordingAgent()
    observation = TargetObservation.from_environment_state(
        _environment_state()
    )
    assert invoke_act(agent, observation) == []
    with pytest.raises(TypeError):
        invoke_act(agent, _oracle())
    assert agent.seen  # the agent only ever saw trusted observations


def test_future_oracle_fields_cannot_enter_target_observation():
    forged = _payload()
    forged["future_close"] = 2500.0
    with pytest.raises((TypeError, ValueError)):
        TargetObservation.from_environment_state(forged)


def _environment_state():
    env = IndianMultiAssetEnvironment(small_config("E1-LEAK").to_env_config())
    env.reset()
    return env._state_at(env.grid[env.index])


def test_actual_indian_state_becomes_target_observation():
    observation = observe_current(
        _fresh_env_for_adapter(),
    )
    assert isinstance(observation, TargetObservation)
    visible, unavailable = split_visibility(observation)
    assert "brent" in unavailable
    assert len(visible) + len(unavailable) == len(
        observation.to_dict()["market"]
    ) + len(observation.to_dict()["macro"])


def _fresh_env_for_adapter():
    env = IndianMultiAssetEnvironment(small_config("E1-LEAK-2").to_env_config())
    env.reset()
    return env


def test_agent_receives_only_trusted_observations_end_to_end():
    agent = RecordingAgent()
    result = run_baseline(agent, small_config("E1-LEAK-3"))
    assert len(agent.seen) == len(result.decision_records)
    for payload in agent.seen:
        assert set(payload) == {
            "decision_timestamp",
            "market",
            "macro",
            "portfolio",
            "calendar",
        }
        assert "future_close" not in str(payload)


def test_adapter_fails_loudly_on_environment_api_drift():
    env = _fresh_env_for_adapter()
    with pytest.raises(TypeError):
        observe_current(object())
    env.done = True
    with pytest.raises(ValueError):
        observe_current(env)


def test_hold_agent_baseline_completes_for_regression():
    result = run_baseline(HoldAgent(), small_config("E1-LEAK-4"))
    assert result.fingerprint()
