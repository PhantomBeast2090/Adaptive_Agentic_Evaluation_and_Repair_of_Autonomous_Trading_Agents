from typing import Dict, Any, Tuple
from .market.historical import HistoricalMarket
from .portfolio.accounting import Portfolio

class FinancialEnvironment:
    def __init__(self, data_path: str, initial_cash: float, transaction_cost_bps: float):
        self.data_path = data_path
        self.market = HistoricalMarket(data_path)
        self.initial_cash = initial_cash
        self.transaction_cost_bps = transaction_cost_bps
        self.portfolio = Portfolio(initial_cash, transaction_cost_bps)
        self.peak_value = initial_cash
        self.current_step = 0
        
    def reset(self) -> Dict[str, Any]:
        self.portfolio = Portfolio(self.initial_cash, self.transaction_cost_bps)
        self.peak_value = self.initial_cash
        self.current_step = 0
        obs = self.market.reset()
        return self._build_obs(obs)
        
    def _build_obs(self, market_obs: Dict[str, Any]) -> Dict[str, Any]:
        if market_obs is None:
            return None
        return {
            "market_data": market_obs,
            "portfolio": {
                "cash": self.portfolio.cash,
                "holdings": self.portfolio.holdings,
                "total_value": self.portfolio.get_value(market_obs["market_price"])
            }
        }
        
    def step(self, action: str, quantity: float) -> Tuple[Dict[str, Any], Dict[str, Any], bool, Dict[str, Any]]:
        self.current_step += 1
        
        # 1. Execute action at CURRENT price
        current_obs = self.market._get_obs()
        current_price = current_obs["market_price"]
        
        # Calculate value before trade to get true step PnL
        previous_val = self.portfolio.get_value(current_price)
        
        tx_fee = self.portfolio.execute_trade(action, quantity, current_price)
        
        # 2. Advance market
        next_market_obs, done = self.market.step()
        
        if done or next_market_obs is None:
            return None, 0.0, True, {}
            
        next_price = next_market_obs["market_price"]
        current_val = self.portfolio.get_value(next_price)
        
        # 3. Calculate metrics
        step_pnl = current_val - previous_val
        cumulative_pnl = current_val - self.initial_cash
        
        if current_val > self.peak_value:
            self.peak_value = current_val
        drawdown = (self.peak_value - current_val) / self.peak_value if self.peak_value > 0 else 0.0
        
        info = {
            "step_pnl": step_pnl,
            "cumulative_pnl": cumulative_pnl,
            "drawdown": drawdown,
            "transaction_costs": tx_fee,
            "date": next_market_obs["date"]
        }
        
        return self._build_obs(next_market_obs), info, done, {}
