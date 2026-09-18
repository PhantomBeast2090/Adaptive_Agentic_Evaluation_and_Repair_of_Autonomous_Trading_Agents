"""E2-B leakage tests (mandate points 21-30, 40)."""

import pytest

from evaluation.contracts.agent import invoke_act
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.contracts.oracle import OraclePacket, TargetObservation
from evaluation.diagnostics.execution import execute
from environment.indian.state import EnvironmentState

from .execution_fixtures import (
    HoldAgent,
    RecordingAgent,
    baseline_spec,  # noqa: F401
    make_episode_config,
    make_exec_state,
    make_null_test,
)


def _oracle():
    return OraclePacket(
        packet_id="O-LEAK",
        source="future_test",
        as_of="2023-05-16",
        content={"nse_equity:RELIANCE:EQ": {"future_close": 9999.0}},
    )


def test_target_receives_only_target_observation(baseline_spec):
    agent = RecordingAgent()
    state = make_exec_state(baseline_spec, "D-LEAK-1")
    execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=agent,
        episode_config=make_episode_config(seed=21),
    )
    assert len(agent.seen) == 10
    for payload in agent.seen:
        assert set(payload) == {
            "decision_timestamp",
            "market",
            "macro",
            "portfolio",
            "calendar",
        }


def test_oracle_packet_rejected(baseline_spec):
    agent = RecordingAgent()
    with pytest.raises(TypeError):
        invoke_act(agent, _oracle())
    assert agent.seen == []


def _foreign_instances():
    from .fixtures import make_prediction, make_proposal, make_result, make_state

    return {
        "state": make_state("D-FOREIGN"),
        "test": make_null_test(),
        "hypothesis": Hypothesis(
            hypothesis_id="H-9",
            failure_class="excessive_turnover",
            mechanism="Overreacts to noise bursts.",
            evidence_refs=("E-1",),
            confidence=0.5,
        ),
        "prediction": make_prediction(),
        "proposal": make_proposal(),
        "result": make_result(),
    }


@pytest.mark.parametrize(
    "foreign_key",
    ["state", "test", "hypothesis", "prediction", "proposal", "result"],
)
def test_diagnostic_objects_rejected_by_invocation_boundary(
    baseline_spec, foreign_key
):
    agent = RecordingAgent()
    instance = _foreign_instances()[foreign_key]
    with pytest.raises(TypeError):
        invoke_act(agent, instance)
    with pytest.raises(TypeError):
        TargetObservation.from_environment_state(instance)
    assert agent.seen == []


def test_no_future_market_information_reaches_target(baseline_spec):
    agent = RecordingAgent()
    state = make_exec_state(baseline_spec, "D-LEAK-3")
    execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=agent,
        episode_config=make_episode_config(seed=22),
    )
    for payload in agent.seen:
        stamp = payload["decision_timestamp"]
        for block in ("market", "macro"):
            for key, slot in payload[block].items():
                obs_date = slot.get("observation_date")
                if obs_date is not None:
                    assert obs_date < stamp, (key, obs_date, stamp)
                values = slot.get("values", {})
                assert "future_close" not in values
                assert "future" not in str(values)


def test_no_direct_environment_state_leakage(baseline_spec):
    seen_types = []

    class TypeRecordingAgent(HoldAgent):
        def act(self, observation):
            seen_types.append(type(observation).__name__)
            if isinstance(observation, EnvironmentState):
                raise AssertionError("raw EnvironmentState reached agent")
            return super().act(observation)

    state = make_exec_state(baseline_spec, "D-LEAK-4")
    execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=TypeRecordingAgent(),
        episode_config=make_episode_config(seed=23),
    )
    assert seen_types == ["TargetObservation"] * 10


def test_no_plain_dictionary_injection(baseline_spec):
    agent = RecordingAgent()
    with pytest.raises(TypeError):
        invoke_act(agent, {"decision_timestamp": "2023-05-15"})
    state = make_exec_state(baseline_spec, "D-LEAK-5")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=agent,
        episode_config=make_episode_config(seed=24),
    )
    assert len(episode.decision_records) == 10


def test_result_references_own_records_not_baseline(baseline_spec):
    from .test_execution_semantics import (
        _baseline_run,
        _state_with_baseline_refs,
    )

    baseline = _baseline_run()
    state = _state_with_baseline_refs(baseline_spec, baseline, "D-LEAK-6")
    episode = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=25),
    )
    # The result references the episode's own trajectory, never the
    # baseline's record objects; separation is structural (own artefact
    # and execution identity), not merely fingerprint inequality — the
    # null control reproduces baseline mechanics by construction.
    assert list(episode.result.record_fps) == [
        r.fingerprint() for r in episode.decision_records
    ]
    assert episode.execution_fingerprint != baseline.fingerprint()
    assert episode.episode_id != baseline.evaluation_id
