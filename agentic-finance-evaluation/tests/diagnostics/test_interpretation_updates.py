"""Update-construction tests (mandate points 11-14, 18-20, 37-38)."""

import pytest

from evaluation.contracts.hypotheses import HypothesisStatus
from evaluation.diagnostics.contracts.hypothesis_updates import (
    Compatibility,
    HypothesisUpdate,
)
from evaluation.diagnostics.interpretation.comparison import Comparison
from evaluation.diagnostics.interpretation.updates import (
    build_update,
    next_confidence,
    next_status,
)

from .fixtures import make_hypothesis, make_prediction, make_test
from .interpretation_fixtures import make_baseline, make_diagnostic_result


def _comparison(compat=Compatibility.SUPPORTS):
    return Comparison(compatibility=compat, detail="fixture detail")


def _built(compat=Compatibility.SUPPORTS):
    baseline = make_baseline({"turnover": 1.0})
    test = make_test()
    result = make_diagnostic_result(baseline, {"turnover": 1.2})
    prediction = make_prediction()
    return build_update(
        update_id="U-1",
        hypothesis=make_hypothesis(),
        prediction=prediction,
        result=result,
        comparison=_comparison(compat),
        observed_repr="1.2",
        control_repr="1.0",
    )


def test_update_references_correct_objects():
    update = _built()
    assert update.hypothesis_id == "H-1"
    assert update.prediction_id == "P-1"
    assert update.result_id == "R-1"
    assert update.compatibility is Compatibility.SUPPORTS
    assert "P-1" in update.assessment
    assert "R-1" in update.assessment


def test_prior_preserved_and_confidence_single_sourced():
    prior = make_hypothesis()
    update = _built()
    assert update.prior == prior
    assert update.prior_fingerprint == prior.fingerprint()
    assert update.updated_confidence == update.updated.confidence
    assert update.evidence_refs == (update.updated.evidence_refs[-1],)
    assert update.prior.fingerprint() != update.updated.fingerprint()


def test_confidence_bounded_and_deterministic():
    assert next_confidence(0.95, Compatibility.SUPPORTS) == 1.0
    assert next_confidence(0.05, Compatibility.CONTRADICTS) == 0.0
    assert next_confidence(0.5, Compatibility.INCONCLUSIVE) == 0.5
    assert next_confidence(0.5, Compatibility.SUPPORTS) == 0.6
    assert next_confidence(0.5, Compatibility.CONTRADICTS) == 0.4
    assert next_confidence(0.5, Compatibility.SUPPORTS) == next_confidence(
        0.5, Compatibility.SUPPORTS
    )
    with pytest.raises(ValueError):
        next_confidence(1.5, Compatibility.SUPPORTS)


@pytest.mark.parametrize(
    "current,compat,expected",
    [
        ("PROPOSED", Compatibility.SUPPORTS, "UNRESOLVED"),
        ("UNRESOLVED", Compatibility.SUPPORTS, "SUPPORTED"),
        ("WEAKENED", Compatibility.SUPPORTS, "UNRESOLVED"),
        ("SUPPORTED", Compatibility.SUPPORTS, "SUPPORTED"),
        ("PROPOSED", Compatibility.CONTRADICTS, "WEAKENED"),
        ("UNRESOLVED", Compatibility.CONTRADICTS, "WEAKENED"),
        ("SUPPORTED", Compatibility.CONTRADICTS, "WEAKENED"),
        ("WEAKENED", Compatibility.CONTRADICTS, "REJECTED"),
        ("PROPOSED", Compatibility.INCONCLUSIVE, "PROPOSED"),
        ("WEAKENED", Compatibility.INCONCLUSIVE, "WEAKENED"),
        ("SUPPORTED", Compatibility.INCONCLUSIVE, "SUPPORTED"),
        ("REJECTED", Compatibility.SUPPORTS, "REJECTED"),
        ("REJECTED", Compatibility.CONTRADICTS, "REJECTED"),
        ("REJECTED", Compatibility.INCONCLUSIVE, "REJECTED"),
    ],
)
def test_lifecycle_ladder(current, compat, expected):
    assert next_status(HypothesisStatus(current), compat) == HypothesisStatus(
        expected
    )


def test_single_supports_never_endorses_or_rejects():
    for current in ("PROPOSED", "UNRESOLVED", "WEAKENED"):
        assert next_status(
            HypothesisStatus(current), Compatibility.SUPPORTS
        ) is not HypothesisStatus.REJECTED
    update = _built(Compatibility.SUPPORTS)
    assert update.updated.status is HypothesisStatus.UNRESOLVED
    assert update.updated.status is not HypothesisStatus.SUPPORTED


def test_mismatched_references_rejected():
    baseline = make_baseline({"turnover": 1.0})
    result = make_diagnostic_result(baseline, {"turnover": 1.2})
    other = make_hypothesis(hypothesis_id="H-9")
    with pytest.raises(ValueError):
        build_update(
            update_id="U-9",
            hypothesis=other,
            prediction=make_prediction(),
            result=result,
            comparison=_comparison(),
            observed_repr="1.2",
            control_repr="1.0",
        )
    with pytest.raises(TypeError):
        build_update(
            update_id="U-9",
            hypothesis=make_hypothesis(),
            prediction="P-1",
            result=result,
            comparison=_comparison(),
            observed_repr="1.2",
            control_repr="1.0",
        )


def test_update_round_trip_and_method_identity():
    update = _built()
    restored = HypothesisUpdate.from_dict(update.to_dict())
    assert restored == update
    assert restored.fingerprint() == update.fingerprint()
    assert update.method == "directional-band"
    assert update.version == "v1"
    assert "directional-band" in update.assessment
    altered = HypothesisUpdate(
        update_id=update.update_id,
        hypothesis_id=update.hypothesis_id,
        prior=update.prior,
        prior_fingerprint=update.prior_fingerprint,
        prediction_id=update.prediction_id,
        result_id=update.result_id,
        compatibility=update.compatibility,
        assessment=update.assessment,
        updated=update.updated,
        updated_confidence=update.updated_confidence,
        evidence_refs=update.evidence_refs,
        method="directional-band-experimental",
        version=update.version,
    )
    assert altered.fingerprint() != update.fingerprint()
    assert update.updated.status is HypothesisStatus.UNRESOLVED
    assert update.updated.evidence_refs[0] == "E-1"
