"""E. DiagnosticTest contract tests."""

import pytest

from evaluation.contracts.diagnostic_tests import DiagnosticTest


def _test_kwargs(**overrides):
    kwargs = {
        "test_id": "T-cost-shift",
        "description": "Raise transaction costs fivefold for one replay.",
        "target_failure_classes": ("excessive_turnover",),
        "intervention": {"type": "transaction_cost_shift", "multiplier": 5.0},
        "measures": ("turnover", "net_pnl"),
        "expected_discrimination": (
            "Cost-sensitive turnover collapses; "
            "noise-driven turnover persists."
        ),
        "estimated_cost": 2.0,
        "preconditions": ("baseline_complete",),
    }
    kwargs.update(overrides)
    return kwargs


def test_valid_test():
    test = DiagnosticTest(**_test_kwargs())
    assert test.intervention["type"] == "transaction_cost_shift"
    assert test.fingerprint()


def test_invalid_test_rejected():
    with pytest.raises(ValueError):
        DiagnosticTest(**_test_kwargs(target_failure_classes=()))
    with pytest.raises(ValueError):
        DiagnosticTest(**_test_kwargs(intervention={"multiplier": 5.0}))
    with pytest.raises(ValueError):
        DiagnosticTest(**_test_kwargs(measures=()))
    with pytest.raises(ValueError):
        DiagnosticTest(**_test_kwargs(estimated_cost=-1.0))
    with pytest.raises(TypeError):
        DiagnosticTest(**_test_kwargs(estimated_cost=True))


def test_fingerprint_covers_every_field():
    base = DiagnosticTest(**_test_kwargs())
    # Per review decision: description is fingerprinted. A semantic change
    # to any field, including prose, changes identity.
    assert (
        DiagnosticTest(
            **_test_kwargs(description="Different prose, same structure.")
        ).fingerprint()
        != base.fingerprint()
    )
    assert (
        DiagnosticTest(**_test_kwargs(estimated_cost=3.0)).fingerprint()
        != base.fingerprint()
    )
    assert (
        DiagnosticTest(
            **_test_kwargs(preconditions=("baseline_complete", "extra"))
        ).fingerprint()
        != base.fingerprint()
    )
    assert DiagnosticTest.from_dict(base.to_dict()).fingerprint() == (
        base.fingerprint()
    )


def test_preconditions_and_serialization():
    test = DiagnosticTest(**_test_kwargs(preconditions=()))
    assert test.preconditions == ()
    restored = DiagnosticTest.from_dict(test.to_dict())
    assert restored == test


def test_nested_intervention_is_immutable():
    test = DiagnosticTest(
        **_test_kwargs(intervention={"type": "shift", "params": {"scale": 2}})
    )
    with pytest.raises(TypeError):
        test.intervention["params"]["scale"] = 3
