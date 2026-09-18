"""E2-B determinism + identity tests (mandate points 1-7, 31-34)."""

import pytest

from evaluation.diagnostics.execution import (
    DiagnosticEpisode,
    execute,
)
from evaluation.diagnostics.execution.episode import DiagnosticEpisodeConfig

from .execution_fixtures import (
    HoldAgent,
    BuyOnceAgent,
    baseline_spec,  # noqa: F401  (module fixture)
    make_cost_test,
    make_episode_config,
    make_exec_state,
    make_null_test,
)


def test_deterministic_execution(baseline_spec):
    kwargs = dict(
        test_id="T-NULL", prediction_ids=("P-1",), target_agent=HoldAgent()
    )
    first = execute(
        diagnostic_state=make_exec_state(baseline_spec, "D-DET-1"),
        episode_config=make_episode_config(seed=7),
        **kwargs,
    )
    second = execute(
        diagnostic_state=make_exec_state(baseline_spec, "D-DET-1"),
        episode_config=make_episode_config(seed=7),
        **kwargs,
    )
    assert first == second
    assert first.fingerprint() == second.fingerprint()
    assert first.execution_fingerprint == second.execution_fingerprint
    assert first.result.fingerprint() == second.result.fingerprint()
    assert [r.fingerprint() for r in first.decision_records] == [
        r.fingerprint() for r in second.decision_records
    ]


def _execute_fresh(baseline_spec, diagnostic_id, agent, test, seed=7, **cfg):
    state = make_exec_state(baseline_spec, diagnostic_id, test=test)
    return execute(
        diagnostic_state=state,
        test_id=test.test_id,
        prediction_ids=("P-1",),
        target_agent=agent,
        episode_config=make_episode_config(seed=seed, **cfg),
    )


def test_seed_change_alters_identity(baseline_spec):
    base = _execute_fresh(
        baseline_spec, "D-SEED", HoldAgent(), make_null_test(), seed=7
    )
    other = _execute_fresh(
        baseline_spec, "D-SEED", HoldAgent(), make_null_test(), seed=8
    )
    assert base.execution_fingerprint != other.execution_fingerprint
    assert base.episode_id != other.episode_id
    assert base.result.result_id != other.result.result_id


def test_intervention_change_alters_identity(baseline_spec):
    base = _execute_fresh(
        baseline_spec, "D-INT", HoldAgent(), make_cost_test(multiplier=5.0)
    )
    other = _execute_fresh(
        baseline_spec, "D-INT", HoldAgent(), make_cost_test(multiplier=10.0)
    )
    assert base.execution_fingerprint != other.execution_fingerprint
    assert base.result.intervention_fingerprint != (
        other.result.intervention_fingerprint
    )


def test_environment_config_change_alters_identity(baseline_spec):
    base = _execute_fresh(
        baseline_spec, "D-ENV", HoldAgent(), make_null_test(), seed=7
    )
    narrow = _execute_fresh(
        baseline_spec,
        "D-ENV",
        HoldAgent(),
        make_null_test(),
        seed=7,
        universe={"nse_equity": ["RELIANCE:EQ"], "mcx_gold": ["GOLDAUG2023"]},
    )
    assert base.execution_fingerprint != narrow.execution_fingerprint
    assert len(narrow.decision_records) == len(base.decision_records)


def test_agent_version_change_alters_identity(baseline_spec):
    base = _execute_fresh(baseline_spec, "D-AG", HoldAgent(), make_null_test())

    class HoldAgentV2(HoldAgent):
        from evaluation.contracts.agent import AgentIdentity

        identity = AgentIdentity("hold-stub", "0.2")

    other = _execute_fresh(
        baseline_spec, "D-AG", HoldAgentV2(), make_null_test()
    )
    assert base.execution_fingerprint != other.execution_fingerprint


def test_description_change_alters_test_and_execution_identity(baseline_spec):
    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    test = make_null_test()
    relabelled = DiagnosticTest(
        test_id="T-NULL",
        description="A different experimental intent.",
        target_failure_classes=tuple(test.target_failure_classes),
        intervention=dict(test.intervention),
        measures=tuple(test.measures),
        expected_discrimination=test.expected_discrimination,
        estimated_cost=test.estimated_cost,
    )
    assert relabelled.fingerprint() != test.fingerprint()
    base = _execute_fresh(baseline_spec, "D-DESC", HoldAgent(), test)
    other = _execute_fresh(baseline_spec, "D-DESC", HoldAgent(), relabelled)
    assert base.execution_fingerprint != other.execution_fingerprint


def test_no_wall_clock_or_random_identity():
    import pathlib

    package = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "evaluation"
        / "diagnostics"
        / "execution"
    )
    assert package.is_dir()
    forbidden = (
        "datetime.now",
        "time.time",
        "uuid",
        "random.",
        "os.getpid",
        "threading.get_ident",
    )
    for path in sorted(package.glob("*.py")):
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token!r}"


def test_serialisation_round_trip(baseline_spec):
    episode = _execute_fresh(
        baseline_spec, "D-RT", BuyOnceAgent(), make_null_test()
    )
    restored = DiagnosticEpisode.from_dict(episode.to_dict())
    assert restored == episode
    assert restored.fingerprint() == episode.fingerprint()
    with pytest.raises(ValueError):
        DiagnosticEpisode.from_dict(
            {**episode.to_dict(), "unknown_field": 1}
        )


def test_repeat_execution_cannot_overwrite(baseline_spec):
    state = make_exec_state(baseline_spec, "D-REP")
    first = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=7),
    )
    assert len(state.test_results) == 1
    with pytest.raises(ValueError):
        execute(
            diagnostic_state=state,
            test_id="T-NULL",
            prediction_ids=("P-1",),
            target_agent=HoldAgent(),
            episode_config=make_episode_config(seed=7),
        )
    assert len(state.test_results) == 1
    assert state.test_results[0].result_id == first.result.result_id
    # A differing seed is a distinct execution and is permitted.
    second = execute(
        diagnostic_state=state,
        test_id="T-NULL",
        prediction_ids=("P-1",),
        target_agent=HoldAgent(),
        episode_config=make_episode_config(seed=9),
    )
    assert second.result.result_id != first.result.result_id
    assert len(state.test_results) == 2


def test_episode_config_validation():
    with pytest.raises(TypeError):
        DiagnosticEpisodeConfig(
            start_date="2023-05-15",
            end_date="2023-05-26",
            universe={"nse_equity": ["RELIANCE:EQ"]},
            seed=True,
        )
    with pytest.raises(ValueError):
        DiagnosticEpisodeConfig(
            start_date="2023-05-26",
            end_date="2023-05-15",
            universe={"nse_equity": ["RELIANCE:EQ"]},
            seed=1,
        )
    with pytest.raises(ValueError):
        DiagnosticEpisodeConfig(
            start_date="2023-05-15",
            end_date="2023-05-26",
            universe={},
            seed=1,
        )
    config = make_episode_config(seed=3)
    assert config.identity_dict()["seed"] == 3
    assert "base_dir" not in config.identity_dict()
    assert config.to_dict()["base_dir"] == "."
