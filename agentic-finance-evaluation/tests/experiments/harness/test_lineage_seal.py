"""Arm transitions, lineage guards, seal mechanics, scope equality."""

import pytest

from experiments.harness.errors import (
    LineageError,
    SealIntegrityError,
    SealedAccessError,
    TransitionError,
)
from experiments.harness.lifecycle import instantiate_agent
from experiments.harness.lineage import (
    SealedBaseline,
    assert_same_scope,
    assert_transition,
    heldout_scope,
    require_repair_lineage,
    require_rh_lineage,
)

from .fixtures import HELD, UNIVERSE, make_baseline


def _scope():
    return heldout_scope(
        heldout_window=HELD,
        universe=dict(UNIVERSE),
        transaction_cost_bps=5.0,
        initial_cash=100000.0,
        strict_pit=True,
        vintage_policy="explicit",
        environment_fingerprint="env-fp",
    )


def _sealed():
    baseline = make_baseline("E-NH", HELD, {"turnover": 1.0})
    return SealedBaseline.seal(payload=baseline, scope=_scope())


def test_allowed_transitions_pass():
    for frm, to in (
        ("N-D", "D-F"),
        ("N-D", "D-A"),
        ("N-H", "SEALED"),
        ("D-F", "REPAIR"),
        ("D-A", "REPAIR"),
        ("REPAIR", "R-D"),
        ("R-D", "R-H"),
        ("R-H", "ASSEMBLY"),
    ):
        assert_transition(frm, to)


def test_forbidden_transitions_raise():
    for frm, to in (
        ("N-D", "R-H"),
        ("N-D", "R-D"),
        ("D-F", "R-H"),
        ("D-A", "R-H"),
        ("N-D", "ASSEMBLY"),
        ("R-D", "ASSEMBLY"),
        ("R-H", "R-D"),
    ):
        with pytest.raises(TransitionError):
            assert_transition(frm, to)


def test_cross_experiment_lineage_reuse_rejected():
    with pytest.raises(TransitionError):
        assert_transition("R-H-OTHER", "ASSEMBLY")


def test_repair_lineage_guards():
    require_repair_lineage("ACCEPTED", "val-fp")
    require_repair_lineage("REJECTED", "val-fp")
    require_repair_lineage("UNRESOLVED", "val-fp")
    with pytest.raises(LineageError):
        require_repair_lineage("FAILED", "val-fp")
    with pytest.raises(LineageError):
        require_repair_lineage("ACCEPTED", "none")
    require_rh_lineage("cand-1", "rep-fp")
    with pytest.raises(LineageError):
        require_rh_lineage("none", "rep-fp")


def test_sealed_contents_locked_before_release():
    sealed = _sealed()
    assert sealed.released is False
    with pytest.raises(SealedAccessError):
        sealed.contents()


def test_release_once_in_assembly_then_double_release_fails():
    sealed = _sealed()
    released = sealed.release(phase="assembly")
    assert released.released is True
    assert released.contents().fingerprint() == (
        sealed.baseline_fingerprint
    )
    with pytest.raises(SealIntegrityError):
        released.release(phase="assembly")


def test_release_wrong_phase_fails():
    with pytest.raises(SealIntegrityError):
        _sealed().release(phase="diagnosis")


def test_tampered_payload_fails_closed():
    sealed = _sealed()
    tampered = make_baseline("E-NH-TAMPERED", HELD, {"turnover": 9.0})
    corrupted = SealedBaseline(
        scope=dict(sealed.scope),
        scope_fingerprint=sealed.scope_fingerprint,
        baseline_fingerprint=sealed.baseline_fingerprint,
        payload=tampered,
        seal_fingerprint=sealed.seal_fingerprint,
        released=False,
        release_note=None,
    )
    with pytest.raises(SealIntegrityError):
        corrupted.release(phase="assembly")


def test_scope_equality_and_mismatch():
    assert_same_scope(_scope(), _scope())
    other = _scope()
    other["transaction_cost_bps"] = 9.0
    with pytest.raises(LineageError):
        assert_same_scope(_scope(), other)


def test_seal_round_trip():
    sealed = _sealed()
    revived = SealedBaseline.from_dict(sealed.to_dict())
    assert revived.to_dict() == sealed.to_dict()
    with pytest.raises(ValueError):
        SealedBaseline.from_dict({**sealed.to_dict(), "zzz": 1})


def test_agent_instances_isolated_per_arm():
    first = instantiate_agent(
        "benchmarks.hold.HoldBenchmark"
    )
    second = instantiate_agent(
        "benchmarks.hold.HoldBenchmark"
    )
    assert first is not second
    assert first.identity.agent_id == second.identity.agent_id
    with pytest.raises(ValueError):
        instantiate_agent("not-a-path")
