import pytest
from evaluation.evaluators.module_b import DiagnosisEvaluator

def test_diagnosis_evaluator():
    evaluator = DiagnosisEvaluator({})
    
    # Test loss chasing detection mock
    trajectory_chase = [
        {
            "observation": {"portfolio": {"total_value": 10000.0, "holdings": 10}, "market_price": 100.0},
            "decision": {"action": "BUY", "quantity": 10},
            "outcome": {"step_pnl": -100.0}
        },
        {
            "observation": {"portfolio": {"total_value": 9900.0, "holdings": 20}, "market_price": 99.0},
            "decision": {"action": "BUY", "quantity": 20},
            "outcome": {"step_pnl": -100.0}
        }
    ]
    
    result = evaluator.diagnose(trajectory_chase)
    assert "increases position size" in result["diagnosed_mechanism"]
    assert result["confidence_score"] == 0.95
