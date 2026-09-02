from typing import Dict, Any
from .base import BaseTradingAgent

class LLMTradingAgent(BaseTradingAgent):
    def __init__(self, agent_id: str, version: str, model_config: Dict[str, Any]):
        super().__init__(agent_id, version)
        self.model_config = model_config
        # Explicit memory context that can be updated via interventions
        self.memory_context = [
            {"role": "system", "content": "You are a rational financial trading agent."}
        ]
        
    def act(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Placeholder for LLM inference.
        In the real implementation, this will construct a prompt using the 
        observation and memory_context, call the LLM, and parse the structured output.
        """
        if not observation:
            return {
                "action": "HOLD",
                "quantity": 0.0,
                "rationale": "No active observation."
            }

        # TODO: Implement actual LLM call with temperature=0 for determinism
        
        # Dummy deterministic logic for testing interfaces
        vix = observation.get("vix", 0.0)
        cash = observation.get("portfolio", {}).get("cash", 0.0)
        price = observation.get("market_price", 1.0)
        
        if vix > 30.0 and cash >= price:
            # High volatility, buy 1 share as a dummy strategy
            return {
                "action": "BUY",
                "quantity": 1.0,
                "rationale": "VIX is high, buying 1 share."
            }
        elif vix < 15.0 and observation.get("portfolio", {}).get("holdings", 0.0) > 0:
            return {
                "action": "SELL",
                "quantity": 1.0,
                "rationale": "VIX is low, selling 1 share."
            }
            
        return {
            "action": "HOLD",
            "quantity": 0.0,
            "rationale": "No strong signal."
        }
        
    def adapt(self, intervention: Dict[str, Any]) -> None:
        """
        Updates the agent's memory context based on the structured intervention.
        """
        rule = intervention.get("behavioral_rule", "")
        trigger = intervention.get("trigger_condition", "")
        desired_behavior = intervention.get("desired_behavior", "")
        
        new_memory = f"NEW RULE: Under condition '{trigger}', you must {desired_behavior}. Specifically: {rule}"
        self.memory_context.append({"role": "system", "content": new_memory})
        self.version = f"{self.version}-adapted"
