"""G. Budget + H. StoppingReason tests."""

import pytest

from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.stopping import StoppingReason


def _budget(**overrides):
    kwargs = {
        "max_episodes": 10,
        "max_tests": 5,
        "max_repairs": 2,
        "max_validation_runs": 2,
        "max_runtime": 3600,
    }
    kwargs.update(overrides)
    return EvaluationBudget(**kwargs)


def test_valid_budget_and_serialization():
    budget = _budget()
    assert EvaluationBudget.from_dict(budget.to_dict()) == budget
    assert budget.fingerprint() == _budget().fingerprint()
    unbounded = _budget(max_tests=None)
    assert unbounded.remaining({})["tests"] is None


def test_invalid_limits_rejected_without_silent_defaults():
    with pytest.raises(ValueError):
        _budget(max_episodes=-1)
    with pytest.raises(TypeError):
        _budget(max_tests=True)
    with pytest.raises(TypeError):
        _budget(max_tests=2.5)
    with pytest.raises(TypeError):
        _budget(max_tests="5")
    with pytest.raises(ValueError):
        EvaluationBudget.from_dict({"max_episodes": 1})
    # Zero is legal: it means "allow none", not "use a default".
    assert _budget(max_repairs=0).remaining({})["repairs"] == 0


def test_exhausted_and_remaining_behavior():
    budget = _budget()
    assert not budget.is_exhausted({"episodes": 9, "tests": 4})
    assert budget.is_exhausted({"episodes": 10})
    assert budget.is_exhausted({"tests": 5})
    assert not budget.is_exhausted({})
    remaining = budget.remaining({"episodes": 3})
    assert remaining["episodes"] == 7
    assert remaining["tests"] == 5
    with pytest.raises(ValueError):
        budget.is_exhausted({"unknown_dimension": 1})
    with pytest.raises(ValueError):
        budget.is_exhausted({"episodes": -1})


def test_stopping_reason_enum_and_serialization():
    assert len(StoppingReason) == 6
    for member in StoppingReason:
        assert StoppingReason.from_str(member.value) is member
        assert member.to_str() == member.value
    with pytest.raises(ValueError):
        StoppingReason.from_str("DONE")
    with pytest.raises(ValueError):
        StoppingReason.from_str("")
    with pytest.raises(ValueError):
        StoppingReason.from_str(None)
