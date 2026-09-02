import os
import yaml
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def test_directories_exist():
    dirs = ['data/raw', 'src/schemas', 'configs', 'tests']
    for d in dirs:
        assert os.path.exists(os.path.join(BASE_DIR, d)), f"Directory {d} does not exist"

def test_config_loads():
    with open(os.path.join(BASE_DIR, 'configs/development.yaml')) as f:
        config = yaml.safe_load(f)
    assert 'environment' in config

def test_schema_instantiation():
    from src.schemas.scenario import Scenario
    s = Scenario(
        scenario_id="test",
        source="FinQA",
        dimension="risk",
        difficulty="hard",
        market_regime="bull",
        information_state={},
        task="predict",
        constraints=[],
        ground_truth={},
        expected_behaviour="hold",
        holdout=False
    )
    assert s.scenario_id == "test"

def test_env_not_exposed():
    assert not os.path.exists(os.path.join(BASE_DIR, '.env')), ".env file should not be committed"
    assert os.path.exists(os.path.join(BASE_DIR, '.env.example')), ".env.example should exist"