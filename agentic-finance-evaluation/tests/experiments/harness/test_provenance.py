"""RQ1 provenance persistence: diagnostic snapshot in Tier-1 assembly.

Hand-built frozen artefacts only — no market episodes. Proves the
pinned projection (hypotheses, updates, stopping reason, uncertainty)
survives persistence deterministically and leaves existing trace,
RQ4, fingerprint, and incident artefacts untouched.
"""

import pytest

from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.contracts.diagnostic_state import (
    UncertaintySnapshot,
)
from experiments.harness.lifecycle import diagnostic_snapshot

from ...diagnostics.fixtures import make_full_state
from .test_rq3_assembly import _pieces as _assembly_pieces


def _full_state():
    state = make_full_state()
    state.record_uncertainty(
        UncertaintySnapshot(
            assessment_id="UA-1",
            method="manual-fixture",
            version="v1",
            open_hypothesis_ids=("H-2",),
            summary="H-1 supported; H-2 open.",
        )
    )
    state.set_stopping_reason(StoppingReason.BUDGET_EXHAUSTED)
    return state


def test_completed_state_is_persisted():
    snapshot = diagnostic_snapshot(_full_state())
    assert set(snapshot) == {
        "hypotheses",
        "hypothesis_updates",
        "stopping_reason",
        "uncertainty",
    }


def test_hypothesis_id_status_confidence_survive():
    snapshot = diagnostic_snapshot(_full_state())
    by_id = {h["id"]: h for h in snapshot["hypotheses"]}
    assert by_id["H-1"]["status"] == "SUPPORTED"
    assert by_id["H-1"]["confidence"] == pytest.approx(0.7)
    assert by_id["H-2"]["status"] == "PROPOSED"
    assert set(by_id["H-1"]) == {"id", "status", "confidence"}


def test_hypothesis_updates_survive():
    snapshot = diagnostic_snapshot(_full_state())
    assert len(snapshot["hypothesis_updates"]) == 1
    update = snapshot["hypothesis_updates"][0]
    assert update["hypothesis_id"] == "H-1"
    assert update["compatibility"] == "SUPPORTS"


def test_stopping_reason_survives():
    snapshot = diagnostic_snapshot(_full_state())
    assert snapshot["stopping_reason"] == "BUDGET_EXHAUSTED"


def test_uncertainty_open_ids_survive():
    snapshot = diagnostic_snapshot(_full_state())
    assert snapshot["uncertainty"] == {"open_hypothesis_ids": ["H-2"]}


def test_snapshot_round_trips_deterministically():
    from evaluation.contracts.fingerprints import fingerprint_of_dict

    first = diagnostic_snapshot(_full_state())
    second = diagnostic_snapshot(_full_state())
    assert first == second
    assert fingerprint_of_dict(first) == fingerprint_of_dict(second)


def test_snapshot_matches_live_state():
    state = _full_state()
    snapshot = diagnostic_snapshot(state)
    live = {h.hypothesis_id: h for h in state.hypotheses}
    assert [h["id"] for h in snapshot["hypotheses"]] == sorted(live)
    for entry in snapshot["hypotheses"]:
        assert entry["status"] == live[entry["id"]].status.value
        assert entry["confidence"] == pytest.approx(
            live[entry["id"]].confidence
        )


def test_assembly_embeds_snapshot_without_changing_trace():
    from experiments.harness.lifecycle import phase_e_assemble

    (config, baseline_nd, sealed, _, repair, report,
     baseline_rd, baseline_rh) = _assembly_pieces()
    result = phase_e_assemble(
        config=config,
        experiment_id="exp-1",
        baseline_nd=baseline_nd,
        sealed_nh=sealed,
        diagnostic_state=make_full_state(),
        diagnostic_trace={"completed": ["T-1"], "invalid_or_failed": []},
        repair_result=repair,
        validation_report=report,
        baseline_rd=baseline_rd,
        baseline_rh=baseline_rh,
    )
    arm_records = result.to_dict()["arm_records"]
    snapshot = arm_records["diagnostic_state_snapshot"]
    assert snapshot["hypotheses"][0]["id"] == "H-1"
    assert arm_records["diagnostic_trace"] == {
        "completed": ["T-1"],
        "invalid_or_failed": [],
    }
    assert result.to_dict()["rq4_vector"]["tests_consumed"] == 1


def test_snapshot_rejects_non_state():
    with pytest.raises(TypeError):
        diagnostic_snapshot({"hypotheses": []})
