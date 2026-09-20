"""Canonical E3 benchmark agents (frozen E3-C substrate).

Single source of truth for research benchmarks. Tests import and reuse
these implementations; benchmark logic is never duplicated in tests.
Test-only failure-injection stubs (broken, outside-universe, exploding
agents) remain test infrastructure and are not benchmarks.
"""

from benchmarks.buy_once import BuyOnceBenchmark
from benchmarks.hold import HoldBenchmark
from benchmarks.volatility_threshold import VolatilityThresholdBenchmark

__all__ = [
    "BuyOnceBenchmark",
    "HoldBenchmark",
    "VolatilityThresholdBenchmark",
]
