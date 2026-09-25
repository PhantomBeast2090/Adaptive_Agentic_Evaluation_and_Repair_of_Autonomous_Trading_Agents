"""Hand-built fixtures for harness unit tests (zero market episodes).

Configurations mirror the frozen E3-C manifest values. Baselines reuse
the E2-F hand-built artefact pattern (one decision record, explicit
metric maps). Nothing here constructs an environment or runs an episode.
"""

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.metrics import MetricResult
from evaluation.baseline.results import BaselineResult
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evaluation_state import EvaluationState
from experiments.harness.config import ExperimentConfig

DIAG = ("2023-05-15", "2023-06-15")
HELD = ("2023-07-10", "2023-08-10")
UNIVERSE = {
    "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
    "mcx_gold": ["GOLDAUG2023"],
}


def make_config(**overrides):
    params = {
        "protocol_version": "E3-D.1",
        "e3d_fingerprint": "e3d-fp-fixture",
        "benchmark_id": "volatility-threshold-benchmark",
        "benchmark_version": "1.0",
        "benchmark_module": (
            "benchmarks.volatility_threshold.VolatilityThresholdBenchmark"
        ),
        "agent_id": "volatility-threshold-benchmark",
        "agent_version": "1.0",
        "environment_fingerprint": "env-fp-fixture",
        "dataset_fingerprints": {"nse_equity": "d1"},
        "calendar_fingerprint": "cal-fp-fixture",
        "diagnostic_window": DIAG,
        "heldout_window": HELD,
        "universe": dict(UNIVERSE),
        "transaction_cost_bps": 5.0,
        "initial_cash": 100000.0,
        "strict_pit": True,
        "vintage_policy": "explicit",
        "diagnostic_policy": "fixed",
        "candidate_pool": (
            "T-null", "T-cost2x", "T-cost0",
            "T-vintage-earliest", "T-uni-tcs", "T-exp-narrow",
        ),
        "fixed_sequence": (
            "T-null", "T-cost2x", "T-uni-tcs",
            "T-vintage-earliest", "T-cost0", "T-exp-narrow",
        ),
        "budgets": {
            "max_tests": 6,
            "max_repairs": 1,
            "max_validation_runs": 3,
        },
        "seed_provenance": 7,
        "arm": "N-D",
        "result_dir": "results/e3",
    }
    params.update(overrides)
    return ExperimentConfig(**params)


def make_manifest(**overrides):
    manifest = {
        "protocol_revision": "E3-C.2",
        "benchmarks": [
            {
                "agent_id": "volatility-threshold-benchmark",
                "version": "1.0",
                "module": (
                    "benchmarks.volatility_threshold."
                    "VolatilityThresholdBenchmark"
                ),
                "fingerprint": "bench-fp-fixture",
            },
            {
                "agent_id": "hold-benchmark",
                "version": "1.0",
                "module": "benchmarks.hold.HoldBenchmark",
                "fingerprint": "hold-fp-fixture",
            },
        ],
        "environment": {
            "universe": {
                "nse_equity": ["RELIANCE:EQ", "TCS:EQ"],
                "mcx_gold": ["GOLDAUG2023"],
            },
            "transaction_cost_bps": 5.0,
            "initial_cash": 100000.0,
        },
        "temporal": {
            "diagnostic_start": "2023-05-15",
            "diagnostic_end": "2023-06-15",
            "heldout_start": "2023-07-10",
            "heldout_end": "2023-08-10",
        },
        "candidate_pool": [
            {"test_id": "T-null",
             "intervention": {"type": "null_intervention"},
             "measures": ["turnover", "order_count"],
             "estimated_cost": 1.0},
            {"test_id": "T-cost2x",
             "intervention": {
                 "type": "transaction_cost_shift", "multiplier": 2.0},
             "measures": ["turnover", "transaction_cost_total"],
             "estimated_cost": 1.0},
            {"test_id": "T-cost0",
             "intervention": {
                 "type": "transaction_cost_set", "costs_bps": 0.0},
             "measures": ["turnover", "transaction_cost_total"],
             "estimated_cost": 1.0},
            {"test_id": "T-vintage-earliest",
             "intervention": {
                 "type": "vintage_policy_shift",
                 "vintage_policy": "earliest_available"},
             "measures": ["turnover", "unavailable_info_rate"],
             "estimated_cost": 1.0},
            {"test_id": "T-uni-tcs",
             "intervention": {
                 "type": "universe_restriction",
                 "nse_equity": ["TCS:EQ"]},
             "measures": ["turnover", "concentration_cost_basis_max"],
             "estimated_cost": 1.0},
            {"test_id": "T-exp-narrow",
             "intervention": {
                 "type": "universe_restriction",
                 "nse_equity": ["RELIANCE:EQ"]},
             "measures": ["gross_exposure_max", "turnover"],
             "estimated_cost": 1.0},
        ],
        "fixed_sequence": {
            "order": [
                "T-null", "T-cost2x", "T-uni-tcs",
                "T-vintage-earliest", "T-cost0", "T-exp-narrow",
            ]
        },
        "budgets": {
            "max_tests": 6,
            "max_repairs": 1,
            "max_validation_runs": 3,
        },
        "hypotheses": [
            {
                "hypothesis_id": "H-turnover",
                "failure_class": "turnover",
                "mechanism": "m",
            },
            {
                "hypothesis_id": "H-exposure",
                "failure_class": "exposure",
                "mechanism": "m2",
            },
        ],
    }
    manifest.update(overrides)
    return manifest


def make_baseline(evaluation_id, window, metrics, agent_id="bench-agent"):
    agent = AgentIdentity(agent_id, "1.0")
    budget = EvaluationBudget(None, None, None, None, None)
    record = DecisionRecord(
        decision_timestamp=window[0],
        state_fingerprint="fp-fixture-1",
        visible_assets=("NIFTY_50",),
        unavailable_assets=("INDIA_VIX",),
        environment_metadata={"market_fingerprint": "mfp-fixture"},
        portfolio_before={"cash": 100000.0, "total_equity": 100000.0},
        portfolio_after={"cash": 100000.0, "total_equity": 100000.0},
    )
    config = BaselineConfig(
        evaluation_id=evaluation_id,
        start_date=window[0],
        end_date=window[1],
        universe={k: tuple(v) for k, v in UNIVERSE.items()},
        budget=budget,
    )
    state = EvaluationState(
        evaluation_id=evaluation_id,
        agent_identity=agent,
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config={},
        budget=budget,
    )
    return BaselineResult(
        evaluation_id=evaluation_id,
        agent_identity=agent,
        environment_spec={"market_fingerprint": "mfp-fixture"},
        config=config,
        decision_records=(record,),
        metrics=tuple(
            MetricResult(
                name=name,
                value=value,
                unit="ratio",
                derivation="e3e.fixture.v1",
            )
            if value is not None
            else MetricResult(
                name=name,
                value=None,
                unit="ratio",
                undefined_reason="no observations in fixture",
                derivation="e3e.fixture.v1",
            )
            for name, value in metrics.items()
        ),
        evidence=(),
        evaluation_state=state,
        stopping_reason=None,
        budget_usage={"episodes": 1},
    )
