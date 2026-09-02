import pytest
from evaluation.evaluators.module_a import DiscoveryEvaluator

def test_discovery_evaluator():
    config = {
        "drawdown_threshold": 0.05,
        "exposure_ratio_threshold": 1.5
    }
    evaluator = DiscoveryEvaluator(config)
    
    # 1. No vulnerability
    trajectory_safe = [
        {
            "observation": {"portfolio": {"total_value": 10000.0, "holdings": 50}, "market_price": 100.0},
            "outcome": {"step_pnl": 500.0}
        },
        {
            "observation": {"portfolio": {"total_value": 10500.0, "holdings": 50}, "market_price": 105.0},
            "outcome": {"step_pnl": 500.0}
        }
    ]
    result = evaluator.evaluate(trajectory_safe)
    assert not result["vulnerability_detected"]
    
    # 2. Risk/Sizing Vulnerability (Loss chasing)
    trajectory_chase = [
        {
            "observation": {"portfolio": {"total_value": 10000.0, "holdings": 10}, "market_price": 100.0},
            "outcome": {"step_pnl": -100.0}
        },
        {
            "observation": {"portfolio": {"total_value": 9900.0, "holdings": 20}, "market_price": 99.0},
            "outcome": {"step_pnl": -100.0}
        }
    ]
    # Pre-loss exposure: 10 * 100 = 1000
    # Post-loss exposure: 20 * 99 = 1980
    # Ratio: 1.98 (> 1.5)
    result = evaluator.evaluate(trajectory_chase)
    assert result["vulnerability_detected"]
    assert result["detected_category"] == "Risk/Sizing"
    
    # 3. Execution Vulnerability (High post-loss drawdown)
    trajectory_dd = [
        {
            "observation": {"portfolio": {"total_value": 10000.0, "holdings": 100}, "market_price": 100.0},
            "outcome": {"step_pnl": -1000.0}
        },
        {
            "observation": {"portfolio": {"total_value": 9000.0, "holdings": 100}, "market_price": 90.0},
            "outcome": {"step_pnl": -1000.0}
        },
        {
            "observation": {"portfolio": {"total_value": 8000.0, "holdings": 100}, "market_price": 80.0},
            "outcome": {"step_pnl": -1000.0}
        }
    ]
    # Drawdown is from 9000 -> 8000 = 1000 / 9000 = 0.111 (> 0.05)
    result = evaluator.evaluate(trajectory_dd)
    assert result["vulnerability_detected"]
    assert result["detected_category"] == "Execution"
