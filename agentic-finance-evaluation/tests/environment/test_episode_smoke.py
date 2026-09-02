import json

import pandas as pd

from agents.financial_agent.synthetic import FlawlessControlAgent
from environment.core import FinancialEnvironment
from src.trace.logger import TraceLogger


def _market_path(tmp_path):
    dates = pd.date_range("2020-01-01", periods=4)
    df = pd.DataFrame(
        {
            "SPY": [100.0, 110.0, 105.0, 107.0],
            "^VIX": [10.0, 10.0, 30.0, 30.0],
        },
        index=dates,
    )
    path = tmp_path / "episode_market.parquet"
    df.to_parquet(path)
    return path


def _run_episode(data_path):
    env = FinancialEnvironment(
        str(data_path),
        initial_cash=1000.0,
        transaction_cost_bps=0.0,
    )
    agent = FlawlessControlAgent("control", "v1")
    agent.reset()
    obs = env.reset()
    trajectory = []
    done = False

    while not done:
        decision = agent.act(obs)
        next_obs, info, done, meta = env.step(
            decision["action"],
            decision["quantity"],
        )
        trajectory.append(
            {
                "observation": obs,
                "next_observation": next_obs,
                "decision": decision,
                "outcome": info,
                "done": done,
                "meta": meta,
            }
        )
        obs = next_obs

    return trajectory


def test_complete_episode_is_deterministic_and_preserves_trajectory(tmp_path):
    data_path = _market_path(tmp_path)

    runs = [_run_episode(data_path) for _ in range(3)]

    assert runs[0] == runs[1] == runs[2]
    assert len(runs[0]) == 4
    assert runs[0][0]["observation"]["date"] == "2020-01-01"
    assert runs[0][0]["observation"]["market_price"] == 100.0
    assert runs[0][0]["observation"]["vix"] == 10.0
    assert runs[0][0]["decision"]["action"] == "BUY"
    assert runs[0][0]["outcome"]["step_pnl"] == 100.0
    assert runs[0][0]["outcome"]["execution_price"] == 100.0
    assert runs[0][0]["outcome"]["portfolio_value"] == 1100.0
    assert runs[0][-1]["observation"]["date"] == "2020-01-04"
    assert runs[0][-1]["outcome"]["date"] == "2020-01-04"
    assert runs[0][-1]["done"] is True


def test_final_timestep_action_executes_and_returns_final_state(tmp_path):
    dates = pd.date_range("2020-01-01", periods=1)
    df = pd.DataFrame({"SPY": [100.0], "^VIX": [10.0]}, index=dates)
    path = tmp_path / "one_row.parquet"
    df.to_parquet(path)

    env = FinancialEnvironment(str(path), initial_cash=1000.0, transaction_cost_bps=10.0)
    obs = env.reset()
    assert obs["date"] == "2020-01-01"

    final_obs, info, done, meta = env.step("BUY", 5.0)

    assert final_obs["date"] == "2020-01-01"
    assert final_obs["portfolio"]["cash"] == 499.5
    assert final_obs["portfolio"]["holdings"] == 5.0
    assert final_obs["portfolio"]["total_value"] == 999.5
    assert info["execution_price"] == 100.0
    assert info["transaction_costs"] == 0.5
    assert info["step_pnl"] == -0.5
    assert info["portfolio_value"] == 999.5
    assert done is True
    assert meta["reason"] == "market_exhausted"


def test_portfolio_invariant_holds_at_every_step(tmp_path):
    data_path = _market_path(tmp_path)
    trajectory = _run_episode(data_path)

    for step in trajectory:
        outcome = step["outcome"]
        valuation_obs = step["next_observation"] if not step["done"] else step["observation"]
        price = valuation_obs["market_price"]
        assert outcome["portfolio_value"] == (
            outcome["cash"] + outcome["holdings"] * price
        )
        assert outcome["cash"] >= 0.0
        assert outcome["holdings"] >= 0.0


def test_observation_does_not_expose_future_market_values(tmp_path):
    data_path = _market_path(tmp_path)
    env = FinancialEnvironment(str(data_path), initial_cash=1000.0, transaction_cost_bps=0.0)
    obs = env.reset()

    assert obs["date"] == "2020-01-01"
    assert obs["market_price"] == 100.0
    assert obs["vix"] == 10.0
    assert "next_market_price" not in obs
    assert "future_return" not in obs
    assert "reward" not in obs

    next_obs, info, done, _ = env.step("HOLD", 0.0)
    assert next_obs["date"] == "2020-01-02"
    assert next_obs["market_price"] == 110.0
    assert info["date"] == "2020-01-02"
    assert done is False


def test_episode_can_be_logged_to_json_and_parquet(tmp_path):
    data_path = _market_path(tmp_path)
    trajectory = _run_episode(data_path)
    logger = TraceLogger(str(tmp_path / "logs"))
    logger.start_episode(
        {
            "episode_id": "phase1_smoke",
            "experiment_seed": 42,
            "phase": "Phase1Audit",
            "agent_version": "v1",
            "dataset_split": "synthetic_unit",
        }
    )

    for step_index, step in enumerate(trajectory):
        logger.log_step(
            step_index,
            step["outcome"]["date"],
            step["observation"],
            step["decision"],
            step["outcome"],
        )

    logger.save()

    json_path = tmp_path / "logs" / "phase1_smoke_Phase1Audit.json"
    parquet_path = tmp_path / "logs" / "phase1_smoke_Phase1Audit_trajectory.parquet"

    assert json_path.exists()
    assert parquet_path.exists()
    with open(json_path, "r") as f:
        logged = json.load(f)
    assert len(logged["trajectory"]) == len(trajectory)
    assert logged["trajectory"][0]["observation"]["market_price"] == 100.0

    logged_df = pd.read_parquet(parquet_path)
    required_columns = {
        "out_execution_price",
        "out_portfolio_value",
        "out_cash",
        "out_holdings",
        "out_transaction_costs",
        "dec_action",
        "dec_quantity",
    }
    assert required_columns.issubset(set(logged_df.columns))
