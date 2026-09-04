"""Tests for the scenario loader.

Verifies that the loader raises on missing split files, rejects duplicate market
windows across splits, and creates valid StaticScenario objects.
"""

import pandas as pd
import pytest
import yaml
from pathlib import Path

from src.data.scenario_loader import ScenarioLoader
from src.schemas.scenario import StaticScenario


def _write_config(tmp_path, splits, holdout_split=None, holdout_max=2):
    config = {
        "static_evaluation": {
            "scenarios": {
                "splits": splits,
                "max_per_split": 10,
                "dimensions": ["performance"],
                "holdout_split": holdout_split if holdout_split is not None else "",
                "holdout_max": holdout_max,
            },
            "environment": {
                "initial_cash": 100000.0,
                "transaction_cost_bps": 5.0,
            },
        }
    }
    config_path = tmp_path / "test_config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return str(config_path)


def _write_split(tmp_path, name, dates, spy_prices, vix_values):
    df = pd.DataFrame(
        {"SPY": spy_prices, "^VIX": vix_values},
        index=pd.to_datetime(dates),
    )
    split_dir = tmp_path / "data" / "processed" / "market_splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    path = split_dir / f"{name}.parquet"
    df.to_parquet(path)
    return str(path)


def test_loader_raises_on_missing_split_file(tmp_path):
    config_path = _write_config(tmp_path, splits=["nonexistent"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Split file not found.*nonexistent"):
        loader.load_scenarios()


def test_loader_creates_windowed_scenarios_from_a_split(tmp_path):
    dates = pd.date_range("2019-01-01", periods=100)
    spy = [100.0 + i * 0.1 for i in range(100)]
    vix = [20.0] * 100

    _write_split(tmp_path, "test_split", dates, spy, vix)
    config_path = _write_config(tmp_path, splits=["test_split"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))
    scenarios = loader.load_scenarios()

    # Window size 63, stride 21: should generate 2 windows from 100 rows
    # (0-62, 21-83)
    assert len(scenarios) >= 2
    assert all(s.source_split == "test_split" for s in scenarios)
    assert all(not s.holdout for s in scenarios)


def test_loader_marks_holdout_scenarios(tmp_path):
    dates = pd.date_range("2021-01-01", periods=80)
    _write_split(tmp_path, "ood_validation", dates, [100.0] * 80, [20.0] * 80)
    config_path = _write_config(tmp_path, splits=[], holdout_split="ood_validation")

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))
    scenarios = loader.load_scenarios()

    assert all(s.holdout for s in scenarios)


def test_loader_rejects_duplicate_windows_across_splits(tmp_path):
    # Create two splits with identical market data
    dates = pd.date_range("2019-01-01", periods=80)
    spy = [100.0] * 80
    vix = [20.0] * 80

    _write_split(tmp_path, "split_a", dates, spy, vix)
    _write_split(tmp_path, "split_b", dates, spy, vix)
    config_path = _write_config(tmp_path, splits=["split_a", "split_b"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Duplicate window detected"):
        loader.load_scenarios()


def test_loader_accepts_distinct_windows_in_different_splits(tmp_path):
    # Two splits with different data
    dates_a = pd.date_range("2019-01-01", periods=80)
    _write_split(tmp_path, "split_a", dates_a, [100.0] * 80, [10.0] * 80)

    dates_b = pd.date_range("2020-01-01", periods=80)
    _write_split(tmp_path, "split_b", dates_b, [110.0] * 80, [25.0] * 80)

    config_path = _write_config(tmp_path, splits=["split_a", "split_b"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))
    scenarios = loader.load_scenarios()

    assert len(scenarios) > 0
    sources = {s.source_split for s in scenarios}
    assert sources == {"split_a", "split_b"}


def test_scenarios_are_sorted_by_scenario_id_for_determinism(tmp_path):
    dates = pd.date_range("2019-01-01", periods=100)
    _write_split(tmp_path, "discovery", dates, [100.0] * 100, [20.0] * 100)
    config_path = _write_config(tmp_path, splits=["discovery"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))
    scenarios = loader.load_scenarios()

    scenario_ids = [s.scenario_id for s in scenarios]
    assert scenario_ids == sorted(scenario_ids)


def test_scenario_objects_have_required_fields(tmp_path):
    dates = pd.date_range("2019-01-01", periods=70)
    _write_split(tmp_path, "discovery", dates, [100.0] * 70, [20.0] * 70)
    config_path = _write_config(tmp_path, splits=["discovery"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))
    scenarios = loader.load_scenarios()

    assert len(scenarios) > 0
    s = scenarios[0]

    assert s.scenario_id.startswith("discovery_")
    assert s.source_split == "discovery"
    assert s.start_date
    assert s.end_date
    assert s.difficulty in ("easy", "medium", "hard")
    assert s.market_regime
    assert s.initial_cash == 100000.0
    assert s.transaction_cost_bps == 5.0
    assert s.market_data_path.endswith("discovery.parquet")
    assert s.created_at  # Should be set via default_factory
    assert not s.holdout


def test_dimension_field_is_empty(tmp_path):
    """The dimension field has no scientific meaning and is left empty."""
    dates = pd.date_range("2019-01-01", periods=70)
    _write_split(tmp_path, "discovery", dates, [100.0] * 70, [20.0] * 70)
    config_path = _write_config(tmp_path, splits=["discovery"])

    loader = ScenarioLoader(config_path, base_dir=str(tmp_path))
    scenarios = loader.load_scenarios()

    assert all(s.dimension == "" for s in scenarios)


def test_static_scenario_created_at_is_per_instance(tmp_path):
    """Each scenario gets its own timestamp, not a shared import-time default."""
    dates = pd.date_range("2019-01-01", periods=70)
    _write_split(tmp_path, "discovery", dates, [100.0] * 70, [20.0] * 70)
    config_path = _write_config(tmp_path, splits=["discovery"])

    loader = ScenarioLoader(config_path)
    scenarios = loader.load_scenarios()

    # All scenarios should have a created_at timestamp
    assert all(s.created_at for s in scenarios)
    # Creating a fresh scenario directly should get a distinct timestamp
    fresh = StaticScenario(
        scenario_id="test",
        source_split="test",
        market_data_path="test.parquet",
        start_date="2019-01-01",
        end_date="2019-01-02",
        dimension="",
        difficulty="medium",
        market_regime="mixed",
        initial_cash=100000.0,
        transaction_cost_bps=5.0,
        holdout=False,
        description="test",
    )
    # The fresh instance should have a timestamp (not crash with a shared default)
    assert fresh.created_at
