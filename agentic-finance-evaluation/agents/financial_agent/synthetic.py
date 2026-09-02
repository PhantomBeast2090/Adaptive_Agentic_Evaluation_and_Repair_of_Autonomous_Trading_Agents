from typing import Dict, Any
from .base import BaseTradingAgent

class FlawlessControlAgent(BaseTradingAgent):
    """
    A baseline agent that trades rationally.
    - Buys when VIX is low (safe environment)
    - Reduces exposure (sells) when VIX spikes (risky environment)
    - Scales positions sensibly.
    """
    def act(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        vix = observation.get("vix", 20.0)
        cash = observation.get("portfolio", {}).get("cash", 0.0)
        holdings = observation.get("portfolio", {}).get("holdings", 0.0)
        price = observation.get("market_price", 1.0)
        
        # Rational rules
        if vix < 15.0 and cash >= price * 10:
            return {"action": "BUY", "quantity": 10.0, "rationale": "VIX is low, building safe exposure."}
        elif vix > 25.0 and holdings > 0:
            return {"action": "SELL", "quantity": holdings, "rationale": "VIX spiked, liquidating for safety."}
            
        return {"action": "HOLD", "quantity": 0.0, "rationale": "Conditions stable, maintaining position."}
        
    def adapt(self, intervention: Dict[str, Any]) -> None:
        pass


class LossChasingAgent(BaseTradingAgent):
    """
    A flawed agent that exhibits the Loss-Chasing vulnerability.
    Escalates position size aggressively after a loss to "win it back".
    """
    def __init__(self, agent_id: str, version: str):
        super().__init__(agent_id, version)
        self.consecutive_losses = 0
        self.previous_value = None
        
    def act(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        cash = observation.get("portfolio", {}).get("cash", 0.0)
        price = observation.get("market_price", 1.0)
        current_value = observation.get("portfolio", {}).get("total_value", 0.0)
        
        # Determine if we just lost money
        if self.previous_value is not None and current_value < self.previous_value:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            
        self.previous_value = current_value
        
        # Loss chasing logic
        if self.consecutive_losses > 0:
            # Escalate quantity exponentially based on consecutive losses
            qty_to_buy = 10.0 * (2 ** self.consecutive_losses)
            max_qty = cash / price
            qty_to_buy = min(qty_to_buy, max_qty)
            
            if qty_to_buy > 0:
                return {"action": "BUY", "quantity": qty_to_buy, "rationale": f"Chasing {self.consecutive_losses} losses, doubling down!"}
                
        # Normal behavior if not chasing
        if cash >= price * 5:
            return {"action": "BUY", "quantity": 5.0, "rationale": "Normal buying."}
            
        return {"action": "HOLD", "quantity": 0.0, "rationale": "Holding."}
        
    def adapt(self, intervention: Dict[str, Any]) -> None:
        self.memory_context.append(intervention)


class VolatilityBlindAgent(BaseTradingAgent):
    """
    A flawed agent that exhibits the Volatility-Blind vulnerability.
    Continues buying regardless of VIX spikes.
    """
    def act(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        cash = observation.get("portfolio", {}).get("cash", 0.0)
        price = observation.get("market_price", 1.0)
        
        # Completely ignores VIX
        if cash >= price * 10:
            return {"action": "BUY", "quantity": 10.0, "rationale": "Always buying 10 shares if I have cash, ignoring VIX."}
            
        return {"action": "HOLD", "quantity": 0.0, "rationale": "Out of cash."}
        
    def adapt(self, intervention: Dict[str, Any]) -> None:
        self.memory_context.append(intervention)
