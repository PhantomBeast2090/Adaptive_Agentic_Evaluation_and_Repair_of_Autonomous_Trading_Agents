import pytest
from datetime import date
from src.schemas.attribution import AttributedDecision, DecisionTimeState
from evaluation.attribution.engine import DecisionAttributionEngine

def test_decision_attribution_engine_initialization():
    engine = DecisionAttributionEngine(base_dir=".")
    assert engine.grid is not None
    assert len(engine.grid) > 0

def test_shift_date():
    engine = DecisionAttributionEngine(base_dir=".")
    # Find a valid date in the grid
    valid_date = engine.grid[10].isoformat()
    shifted = engine._shift_date(valid_date, 1)
    assert shifted == engine.grid[11].isoformat()

def test_attribute_trajectory_structure():
    engine = DecisionAttributionEngine(base_dir=".")
    
    # Mock a decision record dictionary
    mock_record = {
        "decision_timestamp": "2023-02-02",
        "state_fingerprint": "hash123",
        "submitted_orders": [
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "side": "BUY",
                "requested_quantity": 10.0
            }
        ],
        "executions": [
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "execution_status": "EXECUTED_FULL",
                "execution_price": 2500.0
            }
        ],
        "portfolio_before": {"cash": 100000, "total_equity": 100000},
        "portfolio_after": {"cash": 75000, "total_equity": 100000},
        "environment_metadata": {"market_fingerprint": "envhash1"}
    }
    
    result = engine.attribute_trajectory(
        decision_records=[mock_record],
        episode_id="ep1",
        arm="A",
        trajectory_fingerprint="trajhash1",
        run_id="run1",
        experiment_id="exp1"
    )
    
    assert result.arm == "A"
    assert result.activity_count == 1
    assert len(result.attributed_decisions) == 1
    
    decision = result.attributed_decisions[0]
    assert decision.decision_time_state.action == "BUY"
    assert decision.decision_time_state.execution_price == 2500.0
    
    # Outcomes might be None or float depending on InformationLookup
    # But structurally it should distinguish them
    assert hasattr(decision.outcomes, "forward_return_1d")
    assert hasattr(decision.outcomes, "pre_trend_1d")
