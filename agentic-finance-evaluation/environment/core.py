from typing import Any, Dict, Optional, Tuple
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
        self.done = False
        
    def reset(self) -> Dict[str, Any]:
        self.portfolio = Portfolio(self.initial_cash, self.transaction_cost_bps)
        self.peak_value = self.initial_cash
        self.current_step = 0
        self.done = False
        obs = self.market.reset()
        return self._build_obs(obs)
        
    def _build_obs(self, market_obs: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if market_obs is None:
            return None
        return {
            "date": market_obs["date"],
            "market_price": market_obs["market_price"],
            "vix": market_obs["vix"],
            "market_data": market_obs,
            "portfolio": {
                "cash": self.portfolio.cash,
                "holdings": self.portfolio.holdings,
                "total_value": self.portfolio.get_value(market_obs["market_price"])
            }
        }
        
    def step(self, action: str, quantity: float) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], bool, Dict[str, Any]]:
        if self.done:
            current_obs = self.market._get_obs()
            terminal_value = self.portfolio.get_value(current_obs["market_price"])
            return self._build_obs(current_obs), {
                "step_pnl": 0.0,
                "cumulative_pnl": terminal_value - self.initial_cash,
                "drawdown": (
                    (self.peak_value - terminal_value) / self.peak_value
                    if self.peak_value > 0 else 0.0
                ),
                "transaction_costs": 0.0,
                "execution_price": current_obs["market_price"],
                "portfolio_value": terminal_value,
                "cash": self.portfolio.cash,
                "holdings": self.portfolio.holdings,
                "date": current_obs["date"],
            }, True, {"reason": "episode_already_done"}

        self.current_step += 1
        
        # 1. Execute action at CURRENT price
        current_obs = self.market._get_obs()
        current_price = current_obs["market_price"]
        
        # Calculate value before trade to get true step PnL
        previous_val = self.portfolio.get_value(current_price)
        
        tx_fee = self.portfolio.execute_trade(action, quantity, current_price)

        if self.market.current_step >= self.market.max_steps:
            terminal_value = self.portfolio.get_value(current_price)
            if terminal_value > self.peak_value:
                self.peak_value = terminal_value
            drawdown = (
                (self.peak_value - terminal_value) / self.peak_value
                if self.peak_value > 0 else 0.0
            )
            self.done = True
            return self._build_obs(current_obs), {
                "step_pnl": terminal_value - previous_val,
                "cumulative_pnl": terminal_value - self.initial_cash,
                "drawdown": drawdown,
                "transaction_costs": tx_fee,
                "execution_price": current_price,
                "portfolio_value": terminal_value,
                "cash": self.portfolio.cash,
                "holdings": self.portfolio.holdings,
                "date": current_obs["date"],
            }, True, {"reason": "market_exhausted"}
        
        # 2. Advance market
        next_market_obs, done = self.market.step()
        
        if done or next_market_obs is None:
            terminal_value = self.portfolio.get_value(current_price)
            return None, {
                "step_pnl": terminal_value - previous_val,
                "cumulative_pnl": terminal_value - self.initial_cash,
                "drawdown": (
                    (self.peak_value - terminal_value) / self.peak_value
                    if self.peak_value > 0 else 0.0
                ),
                "transaction_costs": tx_fee,
                "execution_price": current_price,
                "portfolio_value": terminal_value,
                "cash": self.portfolio.cash,
                "holdings": self.portfolio.holdings,
                "date": current_obs["date"],
            }, True, {}
            
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
            "execution_price": current_price,
            "portfolio_value": current_val,
            "cash": self.portfolio.cash,
            "holdings": self.portfolio.holdings,
            "date": next_market_obs["date"]
        }
        
        return self._build_obs(next_market_obs), info, done, {}
