"""Deterministic interpretation engine (E2-C).

:func:`interpret` consumes a registered COMPLETED ``DiagnosticTestResult``,
the committed ``HypothesisPrediction`` objects it adjudicates, and the
frozen ``BaselineResult`` control artefact, then records one
``HypothesisUpdate`` per prediction plus a fresh ``UncertaintySnapshot`` —
all through ``DiagnosticState`` ordering rules. Each prediction is assessed
independently: rival hypotheses never compete for a shared verdict, are
never ranked, and receive no posterior scores.

Caller errors (unknown/unregistered result, non-COMPLETED status,
uncommitted or mismatched predictions, baseline identity mismatch,
already-interpreted pairs, stale hypothesis versions) fail explicitly
before any update is created. Evidence insufficiency (missing or undefined
measurement or control) yields ``INCONCLUSIVE`` updates with explicit
reasons — never fabricated values, never silent CONTRADICTS.

The engine reads frozen artefacts only. It never touches the environment,
market data, or the baseline; it creates no tests, proposals, repairs, or
learning state.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from evaluation.baseline.results import BaselineResult
from evaluation.diagnostics.contracts.diagnostic_state import (
    DiagnosticState,
    UncertaintySnapshot,
)
from evaluation.diagnostics.contracts.hypothesis_updates import HypothesisUpdate
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.contracts.test_results import (
    DiagnosticExecutionStatus,
    DiagnosticTestResult,
)
from evaluation.diagnostics.interpretation.comparison import compare
from evaluation.diagnostics.interpretation.methodology import (
    METHOD,
    OPEN_STATUSES,
    VERSION,
)
from evaluation.diagnostics.interpretation.summary import InterpretationRecord
from evaluation.diagnostics.interpretation.updates import build_update


def _resolve_predictions(
    state: DiagnosticState,
    result: DiagnosticTestResult,
    prediction_ids: Sequence[str],
) -> List[HypothesisPrediction]:
    if isinstance(prediction_ids, str) or not isinstance(
        prediction_ids, (tuple, list)
    ):
        raise TypeError("prediction_ids must be a non-empty tuple/list")
    ids = list(prediction_ids)
    if not ids:
        raise ValueError(
            "at least one prediction is required for interpretation"
        )
    committed = {p.prediction_id: p for p in state.predictions}
    resolved = []
    for prediction_id in ids:
        if not isinstance(prediction_id, str) or not prediction_id:
            raise TypeError("prediction ids must be non-empty strings")
        prediction = committed.get(prediction_id)
        if prediction is None:
            raise ValueError(
                f"prediction {prediction_id!r} is not committed: "
                "interpretation requires committed predictions"
            )
        if prediction.test_id != result.test_id:
            raise ValueError(
                f"prediction {prediction_id!r} belongs to test "
                f"{prediction.test_id!r}, not executed test "
                f"{result.test_id!r}"
            )
        if prediction_id not in result.prediction_ids:
            raise ValueError(
                f"prediction {prediction_id!r} is not adjudicated by "
                f"result {result.result_id!r}"
            )
        resolved.append(prediction)
    if len(set(ids)) != len(ids):
        raise ValueError("prediction_ids must not contain duplicates")
    return resolved


def _observed_of(
    result: DiagnosticTestResult, observable: str
) -> Tuple[float | None, str]:
    try:
        measured = result.measured_by_name(observable)
    except KeyError:
        return None, f"no '{observable}' measurement in result"
    if measured.value is None:
        return None, (
            f"'{observable}' explicitly undefined in result: "
            f"{measured.undefined_reason}"
        )
    return float(measured.value), ""


def _control_of(
    baseline: BaselineResult, observable: str
) -> Tuple[float | None, str]:
    try:
        metric = baseline.metric(observable)
    except KeyError:
        return None, f"no '{observable}' metric in baseline artefact"
    if metric.value is None:
        return None, (
            f"'{observable}' explicitly undefined in baseline: "
            f"{metric.undefined_reason}"
        )
    return float(metric.value), ""


def interpret(
    *,
    diagnostic_state: DiagnosticState,
    result_id: str,
    prediction_ids: Sequence[str],
    baseline: BaselineResult,
) -> InterpretationRecord:
    """Interpret one registered result against committed predictions."""
    if not isinstance(diagnostic_state, DiagnosticState):
        raise TypeError(
            "diagnostic_state must be a DiagnosticState, "
            f"got {type(diagnostic_state).__name__}"
        )
    if not isinstance(result_id, str) or not result_id:
        raise TypeError("result_id must be a non-empty string")
    if not isinstance(baseline, BaselineResult):
        raise TypeError(
            "baseline must be a BaselineResult, "
            f"got {type(baseline).__name__}"
        )
    known_results = {r.result_id: r for r in diagnostic_state.test_results}
    result = known_results.get(result_id)
    if result is None:
        raise ValueError(
            f"result {result_id!r} is not registered: "
            "interpretation requires a recorded result"
        )
    if result.status is not DiagnosticExecutionStatus.COMPLETED:
        raise ValueError(
            f"only COMPLETED results may be interpreted; "
            f"{result_id!r} is {result.status.value}"
        )
    if (
        baseline.evaluation_id != result.baseline_evaluation_id
        or baseline.fingerprint() != result.baseline_fingerprint
    ):
        raise ValueError(
            "baseline artefact identity does not match the result's "
            "baseline reference: refusing to compare against a foreign "
            "control"
        )
    predictions = _resolve_predictions(diagnostic_state, result, prediction_ids)

    already = {
        (u.prediction_id, u.result_id)
        for u in diagnostic_state.hypothesis_updates
    }
    for prediction in predictions:
        if (prediction.prediction_id, result.result_id) in already:
            raise ValueError(
                f"prediction {prediction.prediction_id!r} already "
                f"interpreted against result {result.result_id!r}: "
                "evidence must not be double-counted"
            )

    created: List[HypothesisUpdate] = []
    for prediction in predictions:
        hypothesis = diagnostic_state.hypothesis(prediction.hypothesis_id)
        observed_value, _ = _observed_of(result, prediction.predicted_observable)
        control_value, control_reason = _control_of(
            baseline, prediction.predicted_observable
        )
        comparison = compare(
            direction=prediction.expected_direction,
            observed_value=observed_value,
            control_value=control_value,
            control_reason=control_reason or "control unavailable",
        )
        update = build_update(
            update_id=(
                f"{result.result_id}:{prediction.prediction_id}"
                f":u{_existing_update_count(diagnostic_state, hypothesis.hypothesis_id)}"
            ),
            hypothesis=hypothesis,
            prediction=prediction,
            result=result,
            comparison=comparison,
            observed_repr=(
                repr(observed_value)
                if observed_value is not None
                else "absent"
            ),
            control_repr=(
                repr(control_value)
                if control_value is not None
                else f"unavailable ({control_reason})"
            ),
        )
        diagnostic_state.record_update(update)
        created.append(update)

    snapshot = _snapshot(diagnostic_state, result.result_id)
    diagnostic_state.record_uncertainty(snapshot)
    return InterpretationRecord(
        interpretation_id=(
            f"{diagnostic_state.diagnostic_id}:interp:{result.result_id}"
        ),
        diagnostic_id=diagnostic_state.diagnostic_id,
        result_id=result.result_id,
        prediction_ids=tuple(p.prediction_id for p in predictions),
        update_ids=tuple(u.update_id for u in created),
        uncertainty_id=snapshot.assessment_id,
        method=METHOD,
        version=VERSION,
    )


def _existing_update_count(state: DiagnosticState, hypothesis_id: str) -> int:
    return sum(
        1
        for u in state.hypothesis_updates
        if u.hypothesis_id == hypothesis_id
    )


def _snapshot(state: DiagnosticState, result_id: str) -> UncertaintySnapshot:
    open_ids = sorted(
        h.hypothesis_id
        for h in state.hypotheses
        if h.status.value in OPEN_STATUSES
    )
    total = len(state.hypotheses)
    if open_ids:
        parts = ", ".join(
            f"{state.hypothesis(hid).hypothesis_id} "
            f"{state.hypothesis(hid).status.value}@"
            f"{state.hypothesis(hid).confidence:.4f}"
            for hid in open_ids
        )
        summary = (
            f"{METHOD} {VERSION}: {len(open_ids)} open of {total} "
            f"after {result_id}: {parts}."
        )
    else:
        summary = (
            f"{METHOD} {VERSION}: 0 open of {total} after {result_id}."
        )
    return UncertaintySnapshot(
        assessment_id=f"{state.diagnostic_id}:ua:{result_id}",
        method=METHOD,
        version=VERSION,
        open_hypothesis_ids=tuple(open_ids),
        summary=summary,
    )
