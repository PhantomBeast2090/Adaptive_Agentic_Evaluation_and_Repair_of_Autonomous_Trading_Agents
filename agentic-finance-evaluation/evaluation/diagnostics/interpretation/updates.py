"""Construction of frozen HypothesisUpdate objects (E2-C).

:func:`build_update` turns one assessed (hypothesis-version, prediction,
result, comparison) tuple into the exact frozen E2-A contract. It applies
the versioned confidence transition and lifecycle ladder from
``methodology.py`` and formats the deterministic assessment string. It
registers nothing — registration (with stale-prior and duplicate guards)
is the interpreter's job via ``DiagnosticState.record_update``.
"""

from __future__ import annotations

from typing import Tuple

from evaluation.contracts.hypotheses import Hypothesis, HypothesisStatus
from evaluation.diagnostics.contracts.hypothesis_updates import (
    Compatibility,
    HypothesisUpdate,
)
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.contracts.test_results import DiagnosticTestResult
from evaluation.diagnostics.interpretation.comparison import Comparison
from evaluation.diagnostics.interpretation.methodology import (
    CONFIDENCE_STEP_CONTRADICTS,
    CONFIDENCE_STEP_INCONCLUSIVE,
    CONFIDENCE_STEP_SUPPORTS,
    METHOD,
    VERSION,
)

_TRANSITIONS = {
    Compatibility.SUPPORTS: {
        HypothesisStatus.PROPOSED: HypothesisStatus.UNRESOLVED,
        HypothesisStatus.UNRESOLVED: HypothesisStatus.SUPPORTED,
        HypothesisStatus.WEAKENED: HypothesisStatus.UNRESOLVED,
        HypothesisStatus.SUPPORTED: HypothesisStatus.SUPPORTED,
        HypothesisStatus.REJECTED: HypothesisStatus.REJECTED,
    },
    Compatibility.CONTRADICTS: {
        HypothesisStatus.PROPOSED: HypothesisStatus.WEAKENED,
        HypothesisStatus.UNRESOLVED: HypothesisStatus.WEAKENED,
        HypothesisStatus.SUPPORTED: HypothesisStatus.WEAKENED,
        HypothesisStatus.WEAKENED: HypothesisStatus.REJECTED,
        HypothesisStatus.REJECTED: HypothesisStatus.REJECTED,
    },
    Compatibility.INCONCLUSIVE: {
        HypothesisStatus.PROPOSED: HypothesisStatus.PROPOSED,
        HypothesisStatus.UNRESOLVED: HypothesisStatus.UNRESOLVED,
        HypothesisStatus.WEAKENED: HypothesisStatus.WEAKENED,
        HypothesisStatus.SUPPORTED: HypothesisStatus.SUPPORTED,
        HypothesisStatus.REJECTED: HypothesisStatus.REJECTED,
    },
}

_CONFIDENCE_STEPS = {
    Compatibility.SUPPORTS: CONFIDENCE_STEP_SUPPORTS,
    Compatibility.CONTRADICTS: CONFIDENCE_STEP_CONTRADICTS,
    Compatibility.INCONCLUSIVE: CONFIDENCE_STEP_INCONCLUSIVE,
}


def next_confidence(prior: float, compatibility: Compatibility) -> float:
    """Bounded symmetric confidence transition (methodology v1)."""
    if (
        not isinstance(prior, (int, float))
        or isinstance(prior, bool)
        or not 0.0 <= float(prior) <= 1.0
    ):
        raise ValueError("prior confidence must be in [0, 1]")
    if compatibility not in _CONFIDENCE_STEPS:
        raise TypeError(
            f"compatibility must be a Compatibility member, "
            f"got {compatibility!r}"
        )
    return min(1.0, max(0.0, float(prior) + _CONFIDENCE_STEPS[compatibility]))


def next_status(
    current: HypothesisStatus, compatibility: Compatibility
) -> HypothesisStatus:
    """Conservative lifecycle ladder (methodology v1)."""
    if not isinstance(current, HypothesisStatus):
        raise TypeError(
            f"current must be a HypothesisStatus, got {current!r}"
        )
    try:
        return _TRANSITIONS[compatibility][current]
    except KeyError:
        raise TypeError(
            f"compatibility must be a Compatibility member, "
            f"got {compatibility!r}"
        ) from None


def _deduped_refs(prior_refs: Tuple[str, ...], result_fp: str) -> Tuple[str, ...]:
    out = tuple(prior_refs)
    if result_fp not in out:
        out = out + (result_fp,)
    return out


def build_update(
    *,
    update_id: str,
    hypothesis: Hypothesis,
    prediction: HypothesisPrediction,
    result: DiagnosticTestResult,
    comparison: Comparison,
    observed_repr: str,
    control_repr: str,
) -> HypothesisUpdate:
    """Build the frozen update for one assessed prediction/result pair."""
    if not isinstance(hypothesis, Hypothesis):
        raise TypeError(
            f"hypothesis must be a Hypothesis, got {type(hypothesis).__name__}"
        )
    if not isinstance(prediction, HypothesisPrediction):
        raise TypeError(
            "prediction must be a HypothesisPrediction, "
            f"got {type(prediction).__name__}"
        )
    if not isinstance(result, DiagnosticTestResult):
        raise TypeError(
            "result must be a DiagnosticTestResult, "
            f"got {type(result).__name__}"
        )
    from evaluation.diagnostics.interpretation.comparison import Comparison as _C

    if not isinstance(comparison, _C):
        raise TypeError(
            f"comparison must be a Comparison, got {type(comparison).__name__}"
        )
    if prediction.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            "prediction does not belong to the assessed hypothesis"
        )
    if prediction.prediction_id not in result.prediction_ids:
        raise ValueError("result does not adjudicate this prediction")
    new_confidence = next_confidence(
        hypothesis.confidence, comparison.compatibility
    )
    new_status = next_status(hypothesis.status, comparison.compatibility)
    updated = Hypothesis(
        hypothesis_id=hypothesis.hypothesis_id,
        failure_class=hypothesis.failure_class,
        mechanism=hypothesis.mechanism,
        evidence_refs=_deduped_refs(
            hypothesis.evidence_refs, result.fingerprint()
        ),
        confidence=new_confidence,
        alternative_hypotheses=hypothesis.alternative_hypotheses,
        discriminating_tests=hypothesis.discriminating_tests,
        status=new_status,
    )
    assessment = (
        f"[{METHOD} {VERSION}] prediction {prediction.prediction_id} "
        f"on result {result.result_id} "
        f"({prediction.expected_direction.value} "
        f"{prediction.predicted_observable}): observed {observed_repr} vs "
        f"control {control_repr} -> {comparison.compatibility.value} "
        f"({comparison.detail}). prior {hypothesis.status.value}@"
        f"{hypothesis.confidence:.4f} -> {new_status.value}@"
        f"{new_confidence:.4f}."
    )
    return HypothesisUpdate(
        update_id=update_id,
        hypothesis_id=hypothesis.hypothesis_id,
        prior=hypothesis,
        prior_fingerprint=hypothesis.fingerprint(),
        prediction_id=prediction.prediction_id,
        result_id=result.result_id,
        compatibility=comparison.compatibility,
        assessment=assessment,
        updated=updated,
        updated_confidence=new_confidence,
        evidence_refs=(result.fingerprint(),),
        method=METHOD,
        version=VERSION,
    )
