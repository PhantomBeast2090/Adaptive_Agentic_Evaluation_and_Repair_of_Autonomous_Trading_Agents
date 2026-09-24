"""E4-C admission-gate and memory-store tests."""

import pytest

from evaluation.context.extraction import extract_candidate
from evaluation.context.gate import (
    AdmissionDecision,
    AdmissionVerdict,
    adjudicate,
)
from evaluation.context.learned import ContextStatus
from evaluation.context.memory import MemoryStore

from .test_extraction import _artefacts


def _candidate():
    proposal, result, report, analysis = _artefacts()
    candidate = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    return candidate, (proposal, result, report, analysis)


def _admit_all(store=None):
    candidate, (proposal, result, report, analysis) = _candidate()
    store = store or MemoryStore(store_id="mem-1")
    validated, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store,
    )
    return store.admit(validated, verdict), candidate


def test_accepted_valid_evidence_admitted():
    candidate, (proposal, result, report, analysis) = _candidate()
    store = MemoryStore(store_id="mem-1")
    validated, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store,
    )
    assert validated.status is ContextStatus.VALIDATED
    assert verdict.decision is AdmissionDecision.ADMITTED
    assert verdict.fingerprint()
    assert AdmissionVerdict.from_dict(verdict.to_dict()) == verdict
    stored = store.admit(validated, verdict)
    assert stored.store_version == 1
    assert stored.entries[0].context.status is ContextStatus.ADMITTED
    assert stored.entries[0].sequence == 1
    assert store.store_version == 0
    assert stored.fingerprint() != store.fingerprint()


def test_failed_repair_rejected():
    import dataclasses

    from evaluation.diagnostics.repair.results import RepairDecision

    candidate, (proposal, result, report, analysis) = _candidate()
    failed = dataclasses.replace(result, decision=RepairDecision.FAILED)
    _, verdict = adjudicate(
        candidate=candidate,
        result=failed,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
    )
    assert verdict.decision is AdmissionDecision.REJECTED
    assert "ACCEPTED" in verdict.reason


def test_unresolved_and_rejected_repairs_rejected():
    import dataclasses

    from evaluation.diagnostics.repair.results import RepairDecision

    candidate, (proposal, result, report, analysis) = _candidate()
    for decision in (RepairDecision.UNRESOLVED, RepairDecision.REJECTED):
        altered = dataclasses.replace(result, decision=decision)
        _, verdict = adjudicate(
            candidate=candidate,
            result=altered,
            report=report,
            analysis=analysis,
            store=MemoryStore(store_id="mem-1"),
        )
        assert verdict.decision is AdmissionDecision.REJECTED


def test_missing_provenance_rejected():
    import dataclasses

    candidate, (proposal, result, report, analysis) = _candidate()
    # Provenance is constructor-required, so stripping it post-hoc is
    # impossible on the frozen object; assert the requirement instead.
    with pytest.raises(ValueError):
        dataclasses.replace(candidate, provenance={})
    assert candidate.provenance


def test_tampered_verdict_fingerprint_rejected():
    stored, _ = _admit_all()
    entry = stored.entries[0]
    with pytest.raises(ValueError):
        stored.admit(
            entry.context,
            AdmissionVerdict(
                candidate_id="x",
                candidate_fingerprint="wrong-fingerprint",
                decision=AdmissionDecision.ADMITTED,
                reason="forged",
                method="validation-gate",
                method_version="v1",
            ),
        )


def test_duplicate_handling_deterministic():
    stored, candidate = _admit_all()
    _, (proposal, result, report, analysis) = _candidate()
    fresh = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    validated, verdict = adjudicate(
        candidate=fresh,
        result=result,
        report=report,
        analysis=analysis,
        store=stored,
    )
    assert verdict.decision is AdmissionDecision.DUPLICATE
    assert stored.store_version == 1


def test_conflict_quarantines_newcomer():
    import dataclasses

    stored, _ = _admit_all()
    candidate, (proposal, result, report, analysis) = _candidate()
    altered = dataclasses.replace(
        extract_candidate(
            proposal=proposal, result=result, report=report,
            analysis=analysis,
        ),
        corrective_principle="INCREASE turnover via opposite rule",
    )
    validated, verdict = adjudicate(
        candidate=altered,
        result=result,
        report=report,
        analysis=analysis,
        store=stored,
    )
    assert validated.status is ContextStatus.QUARANTINED
    assert verdict.decision is AdmissionDecision.QUARANTINED
    assert stored.store_version == 1


def test_gate_bypass_impossible():
    stored, candidate = _admit_all()
    with pytest.raises(ValueError):
        stored.admit(candidate, None)
    with pytest.raises(ValueError):
        MemoryStore(store_id="mem-1").admit(
            candidate,
            AdmissionVerdict(
                candidate_id=candidate.context_id,
                candidate_fingerprint=candidate.fingerprint(),
                decision=AdmissionDecision.REJECTED,
                reason="no",
                method="validation-gate",
                method_version="v1",
            ),
        )


def test_determinism_across_repeated_construction():
    first, _ = _admit_all()
    second, _ = _admit_all()
    assert first.fingerprint() == second.fingerprint()
    assert first.to_dict() == second.to_dict()
    assert MemoryStore.from_dict(first.to_dict()) == first


def test_immutability_of_stored_representation():
    stored, candidate = _admit_all()
    snapshot = stored.to_dict()
    with pytest.raises(Exception):
        stored.entries[0].context.version = "v9"  # type: ignore[union-attr]
    assert stored.to_dict() == snapshot
    with pytest.raises(ValueError):
        MemoryStore.from_dict({**snapshot, "zzz": 1})


def test_store_version_chain_c0_c1_c2():
    empty = MemoryStore(store_id="mem-1")
    assert empty.store_version == 0
    one, _ = _admit_all(empty)
    assert one.store_version == 1
    assert one.entries[0].entry_id.startswith("mem-")
