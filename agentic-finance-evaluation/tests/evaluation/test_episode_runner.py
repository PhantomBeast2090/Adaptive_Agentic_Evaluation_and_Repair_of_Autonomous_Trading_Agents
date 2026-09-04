"""Tests for the episode runner.

The market fixture is hand-constructed so that every asserted number can be
checked by hand: 4 rows, zero transaction cost, and a control agent whose rules
are fully determined by VIX.
"""

import pandas as pd
import pytest

from agents.financial_agent.base import BaseTradingAgent
from agents.financial_agent.synthetic import FlawlessControlAgent, VolatilityBlindAgent
from environment.core import FinancialEnvironment
from evaluation.episode_runner import Trajectory, run_episode
from src.trace.logger import TraceLogger


def _market(tmp_path, name="market.parquet"):
    dates = pd.date_range("2020-01-01", periods=4)
    df = pd.DataFrame(
        {
            "SPY": [100.0, 110.0, 105.0, 107.0],
            "^VIX": [10.0, 10.0, 30.0, 30.0],
        },
        index=dates,
    )
    path = tmp_path / name
    df.to_parquet(path)
    return str(path)


def _env(tmp_path, **kwargs):
    defaults = {"initial_cash": 1000.0, "transaction_cost_bps": 0.0}
    defaults.update(kwargs)
    return FinancialEnvironment(_market(tmp_path), **defaults)


class _MalformedAgent(BaseTradingAgent):
    """Returns a decision dict with no action key, then a non-dict."""

    def act(self, observation):
        return {"quantity": 5.0} if observation["date"] == "2020-01-01" else "buy some"

    def adapt(self, intervention):
        pass


def test_runner_records_one_step_per_market_row(tmp_path):
    trajectory = run_episode(
        FlawlessControlAgent("control", "v1"), _env(tmp_path), scenario_id="s1"
    )

    assert len(trajectory) == 4
    assert [step["date"] for step in trajectory.steps] == [
        "2020-01-01",
        "2020-01-02",
        "2020-01-03",
        "2020-01-04",
    ]
    assert [step["step_index"] for step in trajectory.steps] == [0, 1, 2, 3]


def test_recorded_observation_is_the_one_the_agent_acted_on(tmp_path):
    trajectory = run_episode(
        FlawlessControlAgent("control", "v1"), _env(tmp_path), scenario_id="s1"
    )

    for step in trajectory.steps:
        assert step["observation"]["date"] == step["date"]

    # VIX 10 on the first row, so the control agent buys 10 shares at 100.
    first = trajectory.steps[0]
    assert first["observation"]["market_price"] == 100.0
    assert first["observation"]["vix"] == 10.0
    assert first["action"]["action"] == "BUY"
    assert first["action"]["quantity"] == 10.0
    assert first["outcome"]["executed_quantity"] == 10.0
    # Marked at the next row's price of 110: 1000 - 1000 + 10*110 = 1100.
    assert first["outcome"]["portfolio_value"] == 1100.0


def test_initial_and_final_state_are_recorded(tmp_path):
    trajectory = run_episode(
        FlawlessControlAgent("control", "v1"), _env(tmp_path), scenario_id="s1"
    )

    assert trajectory.initial_state == {
        "date": "2020-01-01",
        "market_price": 100.0,
        "vix": 10.0,
        "cash": 1000.0,
        "holdings": 0.0,
        "total_value": 1000.0,
    }
    assert trajectory.final_state["date"] == "2020-01-04"
    assert trajectory.final_state["steps_executed"] == 4
    assert trajectory.final_state["termination_reason"] == "market_exhausted"
    assert trajectory.final_state["total_value"] == pytest.approx(
        trajectory.steps[-1]["outcome"]["portfolio_value"]
    )


def test_environment_spec_is_recorded_for_reproducibility(tmp_path):
    env = _env(tmp_path)
    trajectory = run_episode(FlawlessControlAgent("control", "v1"), env, scenario_id="s1")

    spec = trajectory.environment_spec
    assert spec["initial_cash"] == 1000.0
    assert spec["transaction_cost_bps"] == 0.0
    assert spec["market_rows"] == 4
    assert spec["market_fingerprint"] == env.market.fingerprint()


def test_repeated_runs_produce_identical_content_digests(tmp_path):
    path = _market(tmp_path)

    digests = set()
    for _ in range(3):
        env = FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0)
        trajectory = run_episode(
            FlawlessControlAgent("control", "v1"), env, scenario_id="s1"
        )
        digests.add(trajectory.content_digest())

    assert len(digests) == 1


def test_content_digest_ignores_episode_id_and_wall_clock(tmp_path):
    path = _market(tmp_path)
    agent = FlawlessControlAgent("control", "v1")

    a = run_episode(
        agent,
        FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0),
        scenario_id="s1",
        episode_id="episode_a",
    )
    b = run_episode(
        agent,
        FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0),
        scenario_id="s1",
        episode_id="episode_b",
    )

    assert a.episode_id != b.episode_id
    assert a.content_digest() == b.content_digest()


def test_different_agents_produce_different_digests(tmp_path):
    path = _market(tmp_path)

    control = run_episode(
        FlawlessControlAgent("control", "v1"),
        FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0),
        scenario_id="s1",
    )
    blind = run_episode(
        VolatilityBlindAgent("blind", "v1"),
        FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0),
        scenario_id="s1",
    )

    assert control.content_digest() != blind.content_digest()


def test_window_shortens_the_recorded_episode(tmp_path):
    env = FinancialEnvironment(
        _market(tmp_path),
        initial_cash=1000.0,
        transaction_cost_bps=0.0,
        start_date="2020-01-02",
        end_date="2020-01-03",
    )

    trajectory = run_episode(FlawlessControlAgent("control", "v1"), env, scenario_id="s1")

    assert len(trajectory) == 2
    assert [step["date"] for step in trajectory.steps] == ["2020-01-02", "2020-01-03"]


def test_malformed_decisions_are_recorded_not_silently_held(tmp_path):
    trajectory = run_episode(_MalformedAgent("broken", "v1"), _env(tmp_path), scenario_id="s1")

    missing_action = trajectory.steps[0]
    assert missing_action["action"]["action"] is None
    assert missing_action["action"]["malformed_decision"] is False
    assert missing_action["outcome"]["execution_status"] == "NOOP_INVALID_ACTION"

    non_dict = trajectory.steps[1]
    assert non_dict["action"]["malformed_decision"] is True
    assert non_dict["outcome"]["execution_status"] == "NOOP_INVALID_ACTION"

    # A broken agent must not be scored as a HOLD agent.
    assert all(
        step["outcome"]["execution_status"] == "NOOP_INVALID_ACTION"
        for step in trajectory.steps
    )


def test_seed_is_recorded_but_does_not_change_deterministic_behaviour(tmp_path):
    path = _market(tmp_path)

    seeded = run_episode(
        FlawlessControlAgent("control", "v1"),
        FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0),
        scenario_id="s1",
        seed=7,
    )
    unseeded = run_episode(
        FlawlessControlAgent("control", "v1"),
        FinancialEnvironment(path, initial_cash=1000.0, transaction_cost_bps=0.0),
        scenario_id="s1",
        seed=None,
    )

    assert seeded.seed == 7
    assert seeded.to_dict()["seed"] == 7
    assert [s["action"] for s in seeded.steps] == [s["action"] for s in unseeded.steps]


def test_runner_writes_a_trace_when_a_logger_is_supplied(tmp_path):
    logger = TraceLogger(str(tmp_path / "logs"))

    run_episode(
        FlawlessControlAgent("control", "v1"),
        _env(tmp_path),
        scenario_id="s1",
        episode_id="ep_traced",
        logger=logger,
    )

    assert (tmp_path / "logs" / "ep_traced_static_evaluation.json").exists()
    assert (tmp_path / "logs" / "ep_traced_static_evaluation_trajectory.parquet").exists()


def test_trajectory_to_dict_is_json_serialisable(tmp_path):
    import json

    trajectory = run_episode(
        FlawlessControlAgent("control", "v1"), _env(tmp_path), scenario_id="s1"
    )

    restored = json.loads(json.dumps(trajectory.to_dict()))
    assert restored["scenario_id"] == "s1"
    assert len(restored["steps"]) == 4


def test_empty_trajectory_has_length_zero():
    trajectory = Trajectory("ep", "s1", "agent", "v1")

    assert len(trajectory) == 0
    assert trajectory.to_dict()["steps"] == []
