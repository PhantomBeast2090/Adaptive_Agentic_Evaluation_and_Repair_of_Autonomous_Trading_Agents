import pytest
from evaluation.metrics.deterministic import DeterministicMetricsEngine

def test_deterministic_metrics():
    # Construct a dummy trajectory
    # Step 1: Win
    # Step 2: Loss
    # Step 3: Win (Drawdown during post-loss)
    
    trajectory = [
        {
            "observation": {"portfolio": {"total_value": 10000.0, "holdings": 50, "cash": 5000}, "market_price": 100.0},
            "outcome": {"step_pnl": 500.0}
        },
        {
            "observation": {"portfolio": {"total_value": 9000.0, "holdings": 100, "cash": 0}, "market_price": 90.0},
            "outcome": {"step_pnl": -1000.0}
        },
        {
            "observation": {"portfolio": {"total_value": 8100.0, "holdings": 100, "cash": 0}, "market_price": 81.0},
            "outcome": {"step_pnl": -900.0}
        }
    ]
    
    # 1. Post-loss drawdown
    # After step 2 (loss), peak is 9000. Next step is 8100. Drawdown is (9000-8100)/9000 = 0.1
    drawdown = DeterministicMetricsEngine.calculate_conditional_post_loss_drawdown(trajectory)
    assert drawdown == 0.1
    
    # 2. Position exposure ratio
    # Pre-loss (Step 1 -> 2): Step 1 had holdings=50 at 100.0 = 5000.0 exposure.
    # Step 2 had holdings=100 at 90.0 = 9000.0 exposure.
    # Since Step 1 was a win (500), it doesn't trigger the post-loss exposure rule from step 0.
    # Wait, the rule checks if previous step was a loss.
    # Step 1 pnl = 500 (not a loss).
    # Step 2 pnl = -1000 (loss).
    # Pre-loss exposure (Step 2) = 100 * 90 = 9000.
    # Post-loss exposure (Step 3) = 100 * 81 = 8100.
    # Ratio = 8100 / 9000 = 0.9
    ratio = DeterministicMetricsEngine.calculate_position_exposure_ratio(trajectory)
    assert ratio == 0.9
    
    # 3. Cumulative return
    # Initial value = 10000 - 500 = 9500
    # Final value = 8100
    # Return = (8100 - 9500) / 9500 = -1400 / 9500 = -0.147368...
    cum_return = DeterministicMetricsEngine.calculate_cumulative_return(trajectory)
    assert abs(cum_return - (-0.14736842105263157)) < 1e-5
