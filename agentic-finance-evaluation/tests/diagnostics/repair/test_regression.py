"""Regression tests: explicit deltas, None-preservation, tolerance hook."""

import pytest

from evaluation.diagnostics.repair.regression import (
    REGRESSION_METHOD,
    REGRESSION_VERSION,
    RegressionAnalysis,
    RegressionFinding,
    ToleranceRule,
    analyze_regression,
)


def _analysis(**overrides):
    comparisons = overrides.pop(
        "comparisons",
        (
            ("candidate_diagnostic", "turnover", 2.5, 0.4),
            ("candidate_diagnostic", "cumulative_return", 0.02, 0.015),
            ("candidate_heldout", "turnover", 2.2, 0.5),
        ),
    )
    return analyze_regression(
        analysis_id="A-1",
        candidate_id="c",
        validation_fingerprint="vfp",
        comparisons=comparisons,
        **overrides,
    )


def test_deltas_explicit_no_fabrication():
    analysis = _analysis()
    turnover = analysis.finding("turnover", "candidate_diagnostic")
    assert turnover.delta == pytest.approx(0.4 - 2.5)
    assert turnover.reference_value == 2.5
    assert turnover.validation_value == 0.4
    assert turnover.within_tolerance is None
    assert turnover.tolerance is None


def test_undefined_stays_undefined():
    analysis = _analysis(
        comparisons=(
            ("candidate_diagnostic", "sharpe_per_session", None, 0.5),
            ("candidate_diagnostic", "turnover", 2.5, None),
        )
    )
    assert analysis.finding(
        "sharpe_per_session", "candidate_diagnostic"
    ).delta is None
    assert analysis.finding("turnover", "candidate_diagnostic").delta is None
    with pytest.raises(ValueError):
        RegressionFinding(
            metric_name="m", window_label="w", reference_value=1.0,
            validation_value=None, delta=0.5,
        )


def test_tolerance_hook_opt_in_only():
    rule = ToleranceRule(metric_name="turnover", epsilon=0.1)
    assert rule.allows(0.05) is True
    assert rule.allows(0.5) is False
    assert rule.allows(None) is None
    plain = _analysis()
    assert plain.finding("turnover", "candidate_diagnostic").within_tolerance is None
    ruled = _analysis(tolerances=(rule,))
    assert ruled.finding(
        "turnover", "candidate_diagnostic"
    ).within_tolerance is False
    assert ruled.finding(
        "turnover", "candidate_diagnostic"
    ).tolerance["epsilon"] == 0.1
    with pytest.raises(ValueError):
        ToleranceRule(metric_name="m", epsilon=-1.0)
    assert ToleranceRule.from_dict(rule.to_dict()) == rule


def test_analysis_contract_round_trip():
    analysis = _analysis()
    assert analysis.method == REGRESSION_METHOD
    assert analysis.method_version == REGRESSION_VERSION
    restored = RegressionAnalysis.from_dict(analysis.to_dict())
    assert restored == analysis
    assert restored.fingerprint() == analysis.fingerprint()
    with pytest.raises(KeyError):
        analysis.finding("turnover", "no-such-window")
    with pytest.raises(ValueError):
        analyze_regression(
            analysis_id="A-1", candidate_id="c",
            validation_fingerprint="vfp", comparisons=(),
        )
    with pytest.raises(ValueError):
        RegressionAnalysis.from_dict(
            {**analysis.to_dict(), "zzz": 1}
        )
