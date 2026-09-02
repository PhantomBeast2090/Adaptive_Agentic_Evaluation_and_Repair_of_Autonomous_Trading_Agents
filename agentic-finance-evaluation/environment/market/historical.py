import pandas as pd
from typing import Dict, Any, Tuple

class HistoricalMarket:
    def __init__(self, data_path: str):
        self.df = pd.read_parquet(data_path)
        self._validate_data()
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

    def _validate_data(self) -> None:
        required_columns = {"SPY", "^VIX"}
        missing_columns = required_columns.difference(self.df.columns)
        if missing_columns:
            raise ValueError(f"Market data missing required columns: {sorted(missing_columns)}")
        if self.df.empty:
            raise ValueError("Market data must contain at least one row")
        if self.df.index.has_duplicates:
            raise ValueError("Market data index contains duplicate timestamps")
        if not self.df.index.is_monotonic_increasing:
            raise ValueError("Market data index must be sorted in ascending order")
        if self.df[["SPY", "^VIX"]].isna().any().any():
            raise ValueError("Market data contains missing SPY or ^VIX values")
        if (self.df[["SPY", "^VIX"]] <= 0).any().any():
            raise ValueError("Market data contains non-positive SPY or ^VIX values")
