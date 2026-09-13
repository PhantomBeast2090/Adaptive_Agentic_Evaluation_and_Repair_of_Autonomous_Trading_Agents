"""Shared session-scoped fixtures for multi-asset environment tests."""

import pytest

from environment.indian.environment import IndianMultiAssetEnvironment

SMALL_CONFIG = {
    "strict_pit": True,
    "vintage_policy": "explicit",
    "transaction_cost_bps": 5.0,
    "initial_cash": 100000.0,
    "start_date": "2023-05-15",
    "end_date": "2023-05-26",
    "universe": {
        "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
        "mcx_gold": ["GOLDAUG2023"],
    },
}


@pytest.fixture(scope="session")
def indian_env():
    env = IndianMultiAssetEnvironment(dict(SMALL_CONFIG))
    return env


@pytest.fixture()
def fresh_env(indian_env):
    indian_env.reset()
    return indian_env
