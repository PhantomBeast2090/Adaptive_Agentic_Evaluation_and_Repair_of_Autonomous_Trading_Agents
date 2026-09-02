import pandas as pd
from typing import Dict, Any, Tuple

class HistoricalMarket:
    def __init__(self, data_path: str):
        self.df = pd.read_parquet(data_path)
        self.dates = self.df.index.tolist()
        self.current_step = 0
        self.max_steps = len(self.df) - 1
        
    def reset(self) -> Dict[str, Any]:
        self.current_step = 0
        return self._get_obs()
        
    def step(self) -> Tuple[Dict[str, Any], bool]:
        if self.current_step >= self.max_steps:
            return None, True # Done
        self.current_step += 1
        return self._get_obs(), False
        
    def _get_obs(self) -> Dict[str, Any]:
        row = self.df.iloc[self.current_step]
        date = self.dates[self.current_step]
        
        market_price = float(row.get("SPY", 0.0))
        vix = float(row.get("^VIX", 0.0))
        
        return {
            "date": date.strftime("%Y-%m-%d"),
            "market_price": market_price,
            "vix": vix
        }
