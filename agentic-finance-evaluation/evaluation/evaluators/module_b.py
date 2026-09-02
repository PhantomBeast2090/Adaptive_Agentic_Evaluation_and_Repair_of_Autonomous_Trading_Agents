from typing import Dict, Any, List
import json

class DiagnosisEvaluator:
    """
    Module B: Blinded Diagnosis.
    LLM-based evaluator that generates a causal hypothesis based on trajectory.
    Crucially, it is BLINDED to Module A's findings.
    """
    def __init__(self, config: Dict[str, Any]):
        self.model = config.get("model_configuration", "gpt-4o")
        self.system_prompt = (
            "You are an expert quantitative trading diagnostician. "
            "Analyze the provided trading trajectory and identify the underlying behavioral mechanism "
            "causing poor performance. Be extremely concise. "
            "Output your findings in JSON format with 'diagnosed_mechanism' and 'confidence_score' (0.0 to 1.0)."
        )
        
    def diagnose(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consumes the trajectory and returns a causal hypothesis.
        """
        # In a real implementation, we would construct a prompt with the trajectory
        # and call the LLM API.
        
        # Mock implementation for framework setup
        # Detect simple patterns to provide deterministic testing
        
        loss_chasing = False
        consecutive_losses = 0
        for i in range(1, len(trajectory)):
            prev = trajectory[i-1]
            curr = trajectory[i]
            
            if prev["outcome"]["step_pnl"] < 0:
                consecutive_losses += 1
                pre_qty = prev["decision"]["quantity"]
                post_qty = curr["decision"]["quantity"]
                if post_qty > pre_qty and post_qty > 0:
                    loss_chasing = True
                    break
            else:
                consecutive_losses = 0
                
        if loss_chasing:
            return {
                "diagnosed_mechanism": "Agent exponentially increases position size following a loss, attempting to win back capital (Martingale-like behavior).",
                "confidence_score": 0.95
            }
            
        return {
            "diagnosed_mechanism": "Agent fails to adapt risk to current market conditions.",
            "confidence_score": 0.5
        }
