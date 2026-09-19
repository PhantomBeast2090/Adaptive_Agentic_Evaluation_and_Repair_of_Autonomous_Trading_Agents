"""Trace/result contract validation, round-trips, fingerprints."""

import pytest

from evaluation.diagnostics.orchestration.results import OrchestrationResult
from evaluation.diagnostics.orchestration.trace import IterationTraceEntry


def _entry(**overrides):
    payload = {
        "iteration_index": 0,
        "proposal_id": "prop-1",
        "rationale_id": "rat-1",
        "test_id": "T-1",
        "result_id": "R-1",
        "episode_id": "ep-1",
        "execution_fingerprint": "exec-fp-1",
        "interpretation_id": "interp-1",
        "update_ids": ("U-1",),
        "uncertainty_id": "UA-1",
        "pre_state_fingerprint": "pre-fp",
        "post_state_fingerprint": "post-fp",
        "completed": True,
    }
    payload.update(overrides)
    return IterationTraceEntry(**payload)


def test_trace_entry_validation():
    with pytest.raises(ValueError):
        _entry(iteration_index=-1)
    with pytest.raises(ValueError):
        _entry(test_id="  ")
    with pytest.raises(ValueError):
        _entry(
            completed=False, interpretation_id="interp-1",
            update_ids=(), uncertainty_id=None,
        )
    failed = _entry(
        completed=False, interpretation_id=None, update_ids=(),
        uncertainty_id=None,
    )
    assert failed.completed is False
    with pytest.raises(TypeError):
        _entry(update_ids="U-1")
    with pytest.raises(ValueError):
        _entry(update_ids=("U-1", "U-1"))


def test_trace_entry_round_trip_and_fingerprint():
    entry = _entry()
    restored = IterationTraceEntry.from_dict(entry.to_dict())
    assert restored == entry
    assert restored.fingerprint() == entry.fingerprint()
    with pytest.raises(ValueError):
        IterationTraceEntry.from_dict(
            {**entry.to_dict(), "unknown_field": 1}
        )
    with pytest.raises(TypeError):
        IterationTraceEntry.from_dict("not-a-mapping")


def _result(**overrides):
    payload = {
        "diagnostic_id": "D-LOOP",
        "baseline_evaluation_id": "B-LOOP",
        "baseline_fingerprint": "bfp",
        "config_fingerprint": "cfp",
        "iterations": (),
        "terminal_condition": "no_candidate",
        "stopping_reason": None,
        "no_candidate_reason": "nothing eligible",
        "final_state_fingerprint": "final-fp",
        "method": "closed-loop-orchestration",
        "version": "v1",
    }
    payload.update(overrides)
    return OrchestrationResult(**payload)


def test_result_validation_and_dense_indices():
    with pytest.raises(ValueError):
        _result(diagnostic_id=" ")
    first = _entry(iteration_index=0)
    skipped = _entry(iteration_index=2)
    with pytest.raises(ValueError):
        _result(iterations=(first, skipped))
    ok = _result(iterations=(first, _entry(iteration_index=1)))
    assert len(ok.iterations) == 2
    with pytest.raises(TypeError):
        _result(iterations=("nope",))


def test_result_round_trip_and_fingerprint():
    result = _result(iterations=(_entry(),))
    restored = OrchestrationResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.fingerprint() == result.fingerprint()
    with pytest.raises(ValueError):
        OrchestrationResult.from_dict(
            {**result.to_dict(), "unknown_field": 1}
        )
    with pytest.raises(TypeError):
        OrchestrationResult.from_dict("not-a-mapping")
