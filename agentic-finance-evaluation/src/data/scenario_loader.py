"""Static scenario loader for Phase 2 static evaluation.

Loads and creates StaticScenario objects from data splits. Enforces deterministic
scenario ordering and guards against duplicate market windows.
"""

import hashlib
import yaml
import pandas as pd
from pathlib import Path
from typing import List, Set

from src.schemas.scenario import StaticScenario


class ScenarioLoader:
    """Loads static scenarios from data splits based on configuration."""

    def __init__(self, config_path: str = "configs/static_evaluation.yaml", base_dir: str = "."):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['static_evaluation']

        self.base_dir = Path(base_dir)

        # Market regime detection thresholds
        self.vix_high_threshold = 25.0
        self.vix_low_threshold = 15.0

        self._seen_fingerprints: Set[str] = set()
    
    def load_scenarios(self) -> List[StaticScenario]:
        """Load all scenarios based on configuration."""
        scenarios = []

        # Load main evaluation scenarios
        main_scenarios = self._load_scenarios_from_splits(
            splits=self.config['scenarios']['splits'],
            max_per_split=self.config['scenarios']['max_per_split'],
            holdout=False
        )
        scenarios.extend(main_scenarios)

        # Load holdout scenarios if configured
        holdout_split = self.config['scenarios'].get('holdout_split', '')
        if holdout_split:
            holdout_scenarios = self._load_scenarios_from_splits(
                splits=[holdout_split],
                max_per_split=self.config['scenarios']['holdout_max'],
                holdout=True
            )
            scenarios.extend(holdout_scenarios)

        # Sort by scenario_id for deterministic ordering
        scenarios.sort(key=lambda s: s.scenario_id)

        return scenarios
    
    def _load_scenarios_from_splits(
        self,
        splits: List[str],
        max_per_split: int,
        holdout: bool
    ) -> List[StaticScenario]:
        """Load scenarios from specified data splits."""
        scenarios = []

        for split in splits:
            split_path = self.base_dir / "data" / "processed" / "market_splits" / f"{split}.parquet"
            if not split_path.exists():
                raise FileNotFoundError(
                    f"Split file not found: {split_path}. Run data preparation first."
                )

            df = pd.read_parquet(split_path)
            split_scenarios = self._create_scenarios_from_split(
                split_name=split,
                df=df,
                max_scenarios=max_per_split,
                holdout=holdout
            )
            scenarios.extend(split_scenarios)

        return scenarios
    
    def _create_scenarios_from_split(
        self,
        split_name: str,
        df: pd.DataFrame,
        max_scenarios: int,
        holdout: bool
    ) -> List[StaticScenario]:
        """Create scenario objects from a data split."""
        scenarios = []

        # Create time-based windows from the split
        # Each scenario is a contiguous window of market data
        window_size = 63  # ~3 months of trading days
        stride = 21       # ~1 month stride

        dates = df.index
        if len(dates) < window_size:
            # If split is smaller than window, use whole split as one scenario
            window_size = len(dates)
            stride = len(dates)

        scenario_count = 0
        for i in range(0, len(dates) - window_size + 1, stride):
            if scenario_count >= max_scenarios:
                break

            start_idx = i
            end_idx = min(i + window_size, len(dates))

            start_date = dates[start_idx].strftime('%Y-%m-%d')
            end_date = dates[end_idx - 1].strftime('%Y-%m-%d')

            # Guard against duplicate windows across splits
            window_df = df.iloc[start_idx:end_idx]
            fingerprint = self._window_fingerprint(window_df)
            if fingerprint in self._seen_fingerprints:
                raise ValueError(
                    f"Duplicate window detected: {split_name} [{start_date}, {end_date}] "
                    f"has identical market data to a previously loaded window. "
                    f"Check that data splits are distinct or remove duplicate splits from config."
                )
            self._seen_fingerprints.add(fingerprint)

            # Determine market regime for this window
            market_regime = self._detect_market_regime(window_df)

            # Determine difficulty based on regime volatility
            difficulty = self._assess_difficulty(window_df, market_regime)

            scenario_id = f"{split_name}_{start_date}_{end_date}"

            scenario = StaticScenario(
                scenario_id=scenario_id,
                source_split=split_name,
                market_data_path=str(Path(f"data/processed/market_splits/{split_name}.parquet").absolute()),
                start_date=start_date,
                end_date=end_date,
                dimension="",  # Not scientifically meaningful; left empty
                difficulty=difficulty,
                market_regime=market_regime,
                initial_cash=self.config['environment']['initial_cash'],
                transaction_cost_bps=self.config['environment']['transaction_cost_bps'],
                holdout=holdout,
                description=f"{split_name} split from {start_date} to {end_date} ({market_regime} regime)"
            )

            scenarios.append(scenario)
            scenario_count += 1

        return scenarios
    
    def _window_fingerprint(self, df: pd.DataFrame) -> str:
        """SHA-256 fingerprint of a window's (date, SPY, ^VIX) rows.

        Identical to HistoricalMarket.fingerprint() so that duplicate windows
        are detected even when they come from different split files.
        """
        canonical = "\n".join(
            f"{date.strftime('%Y-%m-%d')},{float(spy)!r},{float(vix)!r}"
            for date, spy, vix in zip(df.index, df["SPY"], df["^VIX"])
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _detect_market_regime(self, df: pd.DataFrame) -> str:
        """Detect market regime from VIX and price behavior."""
        if '^VIX' not in df.columns or 'SPY' not in df.columns:
            return "unknown"
        
        avg_vix = df['^VIX'].mean()
        spy_return = (df['SPY'].iloc[-1] / df['SPY'].iloc[0]) - 1
        spy_volatility = df['SPY'].pct_change().std()
        
        if avg_vix > self.vix_high_threshold:
            if spy_return < -0.1:
                return "bear_volatile"
            return "volatile"
        elif avg_vix < self.vix_low_threshold:
            if spy_return > 0.1:
                return "bull_stable"
            return "stable"
        else:
            if spy_return > 0.05:
                return "bull"
            elif spy_return < -0.05:
                return "bear"
            return "mixed"
    
    def _assess_difficulty(self, df: pd.DataFrame, regime: str) -> str:
        """Assess scenario difficulty based on market conditions."""
        if '^VIX' not in df.columns:
            return "medium"
        
        avg_vix = df['^VIX'].mean()
        max_drawdown = self._calculate_max_drawdown(df['SPY'])
        
        # High VIX or large drawdown = hard
        if avg_vix > 30 or max_drawdown > 0.2:
            return "hard"
        # Low VIX and small drawdown = easy
        elif avg_vix < 15 and max_drawdown < 0.05:
            return "easy"
        return "medium"
    
    def _calculate_max_drawdown(self, prices: pd.Series) -> float:
        """Calculate maximum drawdown from price series."""
        peak = prices.expanding().max()
        drawdown = (prices - peak) / peak
        return abs(drawdown.min())


def load_static_scenarios(config_path: str = "configs/static_evaluation.yaml") -> List[StaticScenario]:
    """Convenience function to load static scenarios."""
    loader = ScenarioLoader(config_path)
    return loader.load_scenarios()


if __name__ == "__main__":
    # Test loading
    scenarios = load_static_scenarios()
    print(f"Loaded {len(scenarios)} scenarios:")
    for s in scenarios:
        print(f"  {s.scenario_id}: {s.dimension} | {s.difficulty} | {s.market_regime} | holdout={s.holdout}")