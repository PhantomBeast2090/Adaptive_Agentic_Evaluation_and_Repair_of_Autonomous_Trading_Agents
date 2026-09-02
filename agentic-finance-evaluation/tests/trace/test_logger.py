import os
import json
import pandas as pd
from src.trace.logger import TraceLogger

def test_trace_logger(tmp_path):
    logger = TraceLogger(str(tmp_path))
    
    metadata = {
        "episode_id": "ep_001",
        "experiment_seed": 42,
        "phase": "Discovery",
        "agent_version": "v1.0.0",
        "dataset_split": "discovery"
    }
    
    logger.start_episode(metadata)
    
    obs = {"portfolio": {"cash": 10000, "total_value": 10000}, "market_price": 100, "vix": 20}
    dec = {"action": "BUY", "quantity": 10, "rationale": "test"}
    out = {"step_pnl": 0, "cumulative_pnl": 0, "drawdown": 0, "transaction_costs": 1.0}
    
    logger.log_step(0, "2020-01-01", obs, dec, out)
    
    eval_data = {"detected_category": "Risk/Sizing", "severity": "HIGH"}
    logger.add_evaluation(eval_data)
    
    logger.save()
    
    json_path = tmp_path / "ep_001_Discovery.json"
    parquet_path = tmp_path / "ep_001_Discovery_trajectory.parquet"
    
    assert json_path.exists()
    assert parquet_path.exists()
    
    with open(json_path, "r") as f:
        data = json.load(f)
        assert data["episode_metadata"]["episode_id"] == "ep_001"
        assert len(data["trajectory"]) == 1
        assert data["evaluation"]["detected_category"] == "Risk/Sizing"
        
    df = pd.read_parquet(parquet_path)
    assert len(df) == 1
    assert df.iloc[0]["obs_market_price"] == 100
