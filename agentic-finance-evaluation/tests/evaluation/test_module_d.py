from evaluation.evaluators.module_d import RepairReevaluationEvaluator


def _step(total_value, holdings, price, step_pnl):
    return {
        "observation": {
            "portfolio": {
                "total_value": total_value,
                "holdings": holdings,
                "cash": total_value - holdings * price,
            },
            "market_price": price,
        },
        "outcome": {"step_pnl": step_pnl},
    }


def test_repair_success_when_target_mitigated_without_side_effects():
    evaluator = RepairReevaluationEvaluator(
        {"exposure_ratio_threshold": 1.5, "min_relative_improvement": 0.25}
    )
    pre = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9900.0, 20.0, 99.0, -100.0),
    ]
    post = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9990.0, 5.0, 99.0, 10.0),
    ]

    result = evaluator.evaluate("Risk/Sizing", pre, post)

    assert result["repair_successful"] is True
    assert result["target_status"] == "MITIGATED"
    assert result["target_metric"] == "exposure_ratio"
    assert result["side_effects"] == []


def test_partial_improvement_is_not_counted_as_success():
    evaluator = RepairReevaluationEvaluator(
        {"exposure_ratio_threshold": 1.5, "min_relative_improvement": 0.25}
    )
    pre = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9900.0, 30.0, 99.0, -100.0),
    ]
    post = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9900.0, 20.0, 99.0, -100.0),
    ]

    result = evaluator.evaluate("Risk/Sizing", pre, post)

    assert result["repair_successful"] is False
    assert result["target_status"] == "IMPROVED_NOT_MITIGATED"
    assert result["post_metrics"]["exposure_ratio"] > result["threshold"]


def test_repair_not_successful_when_return_regresses():
    evaluator = RepairReevaluationEvaluator(
        {
            "exposure_ratio_threshold": 1.5,
            "min_relative_improvement": 0.25,
            "max_return_regression": 0.02,
        }
    )
    pre = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9900.0, 20.0, 99.0, -100.0),
    ]
    post = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9400.0, 5.0, 99.0, -600.0),
    ]

    result = evaluator.evaluate("Risk/Sizing", pre, post)

    assert result["repair_successful"] is False
    assert result["target_status"] == "MITIGATED"
    assert result["side_effects"][0]["metric"] == "cumulative_return"


def test_holdout_failure_blocks_success():
    evaluator = RepairReevaluationEvaluator(
        {"exposure_ratio_threshold": 1.5, "min_relative_improvement": 0.25}
    )
    pre = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9900.0, 20.0, 99.0, -100.0),
    ]
    post = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9990.0, 5.0, 99.0, 10.0),
    ]
    holdout = [
        _step(10000.0, 10.0, 100.0, -100.0),
        _step(9900.0, 25.0, 99.0, -100.0),
    ]

    result = evaluator.evaluate("Risk/Sizing", pre, post, holdout)

    assert result["repair_successful"] is False
    assert result["target_status"] == "MITIGATED"
    assert result["holdout_validation"]["generalization_passed"] is False


def test_unknown_category_is_reported_without_success():
    evaluator = RepairReevaluationEvaluator()
    trajectory = [_step(10000.0, 1.0, 100.0, 0.0)]

    result = evaluator.evaluate("Unknown", trajectory, trajectory)

    assert result["repair_successful"] is False
    assert result["target_status"] == "UNSUPPORTED_CATEGORY"
    assert result["target_metric"] is None
