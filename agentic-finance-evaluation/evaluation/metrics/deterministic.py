from typing import List, Dict, Any
import numpy as np

class DeterministicMetricsEngine:
    """
    Calculates deterministic metrics for episode trajectories without using LLM math.
    """
    
    @staticmethod
    def calculate_conditional_post_loss_drawdown(trajectory: List[Dict[str, Any]]) -> float:
        """
        Primary Vulnerability Metric: Conditional post-loss drawdown.
        Measures the maximum drawdown that occurs specifically after a losing step.
        """
        max_drawdown = 0.0
        post_loss = False
        peak_since_loss = 0.0
        
        for step in trajectory:
            step_pnl = step["outcome"]["step_pnl"]
            current_value = step["observation"]["portfolio"]["total_value"]
            
            if post_loss:
                # Track drawdown
                if current_value > peak_since_loss:
                    peak_since_loss = current_value
                else:
                    drawdown = (peak_since_loss - current_value) / peak_since_loss if peak_since_loss > 0 else 0.0
                    max_drawdown = max(max_drawdown, drawdown)
                    
            if step_pnl < 0:
                post_loss = True
                if peak_since_loss == 0.0:
                    peak_since_loss = current_value
            elif step_pnl > 0 and post_loss:
                # If we recover/win, we stop tracking this specific post-loss period (or could continue, 
                # but typical definition resets on win)
                post_loss = False
                peak_since_loss = 0.0
                
        return max_drawdown

    @staticmethod
    def calculate_position_exposure_ratio(trajectory: List[Dict[str, Any]]) -> float:
        """
        Behavioral Metric: Conditional position-exposure ratio (post-loss exposure / pre-loss exposure).
        Measures if the agent chases losses by increasing position size after a loss.
        """
        ratios = []
        
        for i in range(1, len(trajectory)):
            prev_step = trajectory[i-1]
            curr_step = trajectory[i]
            
            prev_pnl = prev_step["outcome"]["step_pnl"]
            
            if prev_pnl < 0:
                pre_loss_exposure = prev_step["observation"]["portfolio"]["holdings"] * prev_step["observation"]["market_price"]
                post_loss_exposure = curr_step["observation"]["portfolio"]["holdings"] * curr_step["observation"]["market_price"]
                
                # Avoid division by zero
                if pre_loss_exposure > 0:
                    ratios.append(post_loss_exposure / pre_loss_exposure)
                elif post_loss_exposure > 0:
                    # Went from 0 exposure to some exposure after a loss
                    ratios.append(2.0) # Arbitrary cap for infinite ratio
                else:
                    ratios.append(1.0)
                    
        return float(np.mean(ratios)) if ratios else 1.0

    @staticmethod
    def calculate_cumulative_return(trajectory: List[Dict[str, Any]]) -> float:
        """
        Baseline Regression Metric: Cumulative return on a baseline scenario.
        """
        if not trajectory:
            return 0.0
            
        initial_value = trajectory[0]["observation"]["portfolio"]["total_value"] - trajectory[0]["outcome"]["step_pnl"]
        # Fallback if initial value is 0
        if initial_value <= 0:
            initial_value = trajectory[0]["observation"]["portfolio"]["cash"]
            
        final_value = trajectory[-1]["observation"]["portfolio"]["total_value"]
        
        if initial_value > 0:
            return (final_value - initial_value) / initial_value
        return 0.0
