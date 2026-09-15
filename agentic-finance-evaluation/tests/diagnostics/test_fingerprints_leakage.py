"""Points 15-17: deterministic fingerprints, clock exclusion, leakage."""

import pytest

from evaluation.contracts.oracle import OraclePacket, TargetObservation
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState

from .fixtures import make_full_state, make_prediction, make_result


def _fingerprint_of(payload):
    from evaluation.contracts.fingerprints import fingerprint_of_dict

    return fingerprint_of_dict(payload)


def test_deterministic_fingerprints():
    first = make_full_state()
    second = make_full_state()
    assert first.fingerprint() == second.fingerprint()
    assert first.to_dict() == second.to_dict()
    altered = make_full_state()
    from evaluation.diagnostics.contracts.diagnostic_state import (
        UncertaintySnapshot,
    )

    altered.record_uncertainty(
        UncertaintySnapshot(
            assessment_id="UA-9",
            method="m",
            version="v",
            open_hypothesis_ids=(),
            summary="Changed summary.",
        )
    )
    assert altered.fingerprint() != first.fingerprint()
    # Mapping order never affects identity.
    assert _fingerprint_of({"b": 1, "a": 2}) == _fingerprint_of({"a": 2, "b": 1})


def test_wall_clock_fields_excluded_from_identity():
    import pathlib

    package = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "evaluation"
        / "diagnostics"
        / "contracts"
    )
    forbidden = ("datetime.now", "time.time", "uuid.", "random.", "os.getpid")
    for path in sorted(package.glob("*.py")):
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token!r}"
    prediction = make_prediction()
    assert "created_at" not in prediction.to_dict()
    assert "timestamp" not in prediction.to_dict()
    result = make_result()
    assert "created_at" not in result.to_dict()
    state_fp_before = make_full_state().fingerprint()
    assert make_full_state().fingerprint() == state_fp_before


def test_target_agent_leakage_boundary_preserved():
    from evaluation.contracts.agent import invoke_act
    from evaluation.contracts.diagnostic_tests import DiagnosticTest

    from .fixtures import HoldAgentStub, make_hypothesis, make_test

    agent = HoldAgentStub()
    oracle = OraclePacket(
        packet_id="O-1",
        source="test",
        as_of="2023-05-15",
        content={"future": True},
    )
    with pytest.raises(TypeError):
        invoke_act(agent, oracle)
    with pytest.raises(TypeError):
        TargetObservation.from_environment_state(
            {"decision_timestamp": "2023-05-15"}
        )
    # Diagnostic-domain objects are never valid observations either.
    for foreign in (
        make_prediction(),
        make_result(),
        make_hypothesis(),
        make_test(),
    ):
        with pytest.raises(TypeError):
            invoke_act(agent, foreign)
        with pytest.raises(TypeError):
            TargetObservation.from_environment_state(foreign)
    assert not isinstance(
        DiagnosticTest(test_id="T-x", description="d",
                       target_failure_classes=("c",),
                       intervention={"type": "t"}, measures=("m",),
                       expected_discrimination="e").to_dict(),
        TargetObservation,
    )


def test_baseline_artefact_counterfactual_separation():
    import pathlib

    package = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "evaluation"
        / "diagnostics"
        / "contracts"
    )
    # No diagnostic contract may import or name the baseline artefact or
    # the environment: references travel by fingerprint strings only, so
    # no code path can mutate baseline records.
    forbidden = ("BaselineResult", "IndianMultiAssetEnvironment", "env.step")
    for path in sorted(package.glob("*.py")):
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token!r}"
    state = make_full_state()
    assert state.baseline_evaluation_id == "B-1"
    assert state.baseline_fingerprint == "baseline-fp-1"
    for result in state.test_results:
        assert result.baseline_fingerprint == "baseline-fp-1"
