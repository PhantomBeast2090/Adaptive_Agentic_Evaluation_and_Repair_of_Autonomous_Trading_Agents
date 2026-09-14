"""E1 runner tests: execution, records, environment semantics."""

import pytest

from evaluation.baseline import BaselineConfig, run_baseline
from evaluation.baseline.trusted import observe_current
from evaluation.contracts.budget import EvaluationBudget
from environment.indian.environment import IndianMultiAssetEnvironment
from environment.indian.information_lookup import InformationLookup

from .stubs import (
    BrokenAgent,
    BuyOnceAgent,
    ChurnAgent,
    HoldAgent,
    OutsideUniverseAgent,
    small_config,
)


def test_compliant_agent_executes_one_record_per_session():
    result = run_baseline(HoldAgent(), small_config("E1-RUN-01"))
    assert len(result.decision_records) == 10
    stamps = [r.decision_timestamp for r in result.decision_records]
    assert stamps == sorted(stamps)
    assert len({r.state_fingerprint for r in result.decision_records}) == 10
    for record in result.decision_records:
        assert record.agent_metadata is None
        assert record.environment_metadata["market_fingerprint"] == (
            result.environment_spec["market_fingerprint"]
        )


def test_invalid_agent_rejected_before_execution():
    with pytest.raises(TypeError):
        run_baseline(object(), small_config("E1-RUN-02"))
    with pytest.raises(TypeError):
        run_baseline("not-an-agent", small_config("E1-RUN-02b"))


def test_reward_equals_env_portfolio_delta_on_every_record():
    result = run_baseline(BuyOnceAgent(), small_config("E1-RUN-03"))
    for record in result.decision_records:
        after = record.portfolio_after["total_equity"]
        before = record.portfolio_before["total_equity"]
        assert record.reward == after - before
    curve = [result.decision_records[0].portfolio_before["total_equity"]]
    curve += [r.portfolio_after["total_equity"] for r in result.decision_records]
    assert sum(r.reward for r in result.decision_records) == (
        curve[-1] - curve[0]
    )


def test_actual_execution_captured_at_session_close():
    result = run_baseline(BuyOnceAgent(), small_config("E1-RUN-04"))
    first = result.decision_records[0]
    assert first.validation[0]["status"] == "VALIDATED"
    execution = first.executions[0]
    assert execution["execution_status"] == "EXECUTED_FULL"
    # Decision at grid[0]=2023-05-15 sees bars through 05-12; the fill is
    # the 05-15 session close reported by the environment itself.
    lookup = InformationLookup(base_dir=".")
    expected = lookup.bar_close(
        "nse_equity", {"symbol": "RELIANCE", "series": "EQ"}, "2023-05-15"
    )
    assert execution["execution_price"] == expected == 2489.25
    assert first.execution_price == expected
    assert first.transaction_cost > 0


def test_invalid_order_behaviour_preserved_with_reason_codes():
    result = run_baseline(OutsideUniverseAgent(), small_config("E1-RUN-05"))
    for record in result.decision_records:
        assert (
            record.executions[0]["execution_status"]
            == "NOOP_INSTRUMENT_OUTSIDE_UNIVERSE"
        )
        assert record.executions[0]["executed_quantity"] == 0.0
        assert (
            record.validation[0]["status"]
            == "NOOP_INSTRUMENT_OUTSIDE_UNIVERSE"
        )
    assert result.metric("universe_violation_count").value == 10.0
    assert result.metric("invalid_order_rate").value == 1.0


def test_unavailable_information_preserved_in_records():
    result = run_baseline(HoldAgent(), small_config("E1-RUN-06"))
    # Brent has 100% NULL availability: strict PIT keeps it invisible on
    # every session; the record carries that fact instead of a price.
    for record in result.decision_records:
        assert "brent" in record.unavailable_assets
        assert "brent" not in record.visible_assets
    assert result.metric("unavailable_info_rate").value == 1.0


def test_configured_universe_preserved_end_to_end():
    config = small_config("E1-RUN-07")
    result = run_baseline(HoldAgent(), config)
    assert list(result.environment_spec["equity_universe"]) == [
        "RELIANCE:EQ",
        "TCS:EQ",
    ]
    assert list(result.environment_spec["gold_universe"]) == ["GOLDAUG2023"]
    env = IndianMultiAssetEnvironment(config.to_env_config())
    assert set(result.environment_spec["equity_universe"]) == (
        env.allowed_instruments["nse_equity"]
    )


def test_malformed_agent_output_fails_closed_without_result():
    with pytest.raises(TypeError):
        run_baseline(BrokenAgent(), small_config("E1-RUN-08"))


def test_empty_window_propagates_environment_error():
    with pytest.raises(ValueError):
        small_config("E1-RUN-09", start_date="2023-05-26", end_date="2023-05-15")
    # 2023-05-20 is a Saturday: no NSE_CM sessions, env refuses the window.
    saturday = small_config(
        "E1-RUN-09b", start_date="2023-05-20", end_date="2023-05-20"
    )
    with pytest.raises(ValueError):
        run_baseline(HoldAgent(), saturday)


def test_single_session_window_yields_explicit_undefined_metrics():
    config = small_config(
        "E1-RUN-10", start_date="2023-05-15", end_date="2023-05-15"
    )
    result = run_baseline(HoldAgent(), config)
    assert len(result.decision_records) == 1
    assert result.metric("sharpe_per_session").value is None
    assert result.metric("sharpe_per_session").undefined_reason
    assert result.metric("cumulative_return").value == 0.0
    assert result.fingerprint()


def test_churn_agent_produces_reversal_evidence():
    result = run_baseline(ChurnAgent(), small_config("E1-RUN-11"))
    reversal = result.metric("reversal_rate")
    assert reversal.value is not None and reversal.value > 0
    assert result.metric("order_count").value == 10.0
