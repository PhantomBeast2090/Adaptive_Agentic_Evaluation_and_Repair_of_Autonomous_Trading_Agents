"""Adversarial validation of E4-A–E4-C scientific invariants.

Each test attacks the memory-admission boundary the way a careless
caller, a forged artefact chain, or a future refactor would: direct
insertion, inconsistent provenance, status smuggling, weakened
checks, nondeterminism, aliasing, and historical contamination.
Zero market episodes; hand-built frozen artefacts only.
"""

import dataclasses
import pathlib
import subprocess
import sys

import pytest

from evaluation.context.extraction import extract_candidate
from evaluation.context.gate import (
    AdmissionDecision,
    AdmissionVerdict,
    adjudicate,
)
from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.memory import MemoryStore
from evaluation.diagnostics.repair.results import RepairDecision

from .test_extraction import _artefacts


def _fresh():
    proposal, result, report, analysis = _artefacts()
    candidate = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    return candidate, proposal, result, report, analysis


def _admit(candidate, proposal, result, report, analysis, store=None):
    store = store if store is not None else MemoryStore(store_id="mem-1")
    validated, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store,
        proposal=proposal,
    )
    return store.admit(validated, verdict), validated, verdict


# -- 1. direct insertion / gate bypass -------------------------------

def test_direct_insert_arbitrary_context_fails():
    candidate, *_ = _fresh()
    store = MemoryStore(store_id="mem-1")
    with pytest.raises(ValueError):
        store.admit(candidate, None)
    forged = AdmissionVerdict(
        candidate_id=candidate.context_id,
        candidate_fingerprint=candidate.fingerprint(),
        decision=AdmissionDecision.ADMITTED,
        reason="forged",
        method="validation-gate",
        method_version="v1",
    )
    # CANDIDATE-status objects are refused even with a matching verdict:
    # only VALIDATED objects pass the gate-to-store handoff.
    with pytest.raises(ValueError):
        store.admit(candidate, forged)


def test_constructed_admitted_object_still_needs_gate():
    candidate, *_ = _fresh()
    smuggled = dataclasses.replace(candidate, status="ADMITTED")
    assert smuggled.status is ContextStatus.ADMITTED
    # ...but the store demands gated provenance, not bare status:
    with pytest.raises(ValueError):
        MemoryStore(store_id="mem-1").admit(
            smuggled,
            AdmissionVerdict(
                candidate_id=smuggled.context_id,
                candidate_fingerprint=smuggled.fingerprint(),
                decision=AdmissionDecision.ADMITTED,
                reason="forged",
                method="validation-gate",
                method_version="v1",
            ),
        )


def test_forgery_is_detectable_by_readjudication():
    candidate, proposal, result, report, analysis = _fresh()
    forged_verdict = AdmissionVerdict(
        candidate_id=candidate.context_id,
        candidate_fingerprint="0" * 64,
        decision=AdmissionDecision.ADMITTED,
        reason="forged",
        method="validation-gate",
        method_version="v1",
    )
    with pytest.raises(ValueError):
        MemoryStore(store_id="mem-1").admit(
            candidate.with_status(ContextStatus.VALIDATED), forged_verdict
        )
    # Honest re-adjudication of the same inputs disagrees with any
    # forgery that misstates fingerprints or decisions.
    _, honest = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=proposal,
    )
    assert honest.decision is AdmissionDecision.ADMITTED
    assert honest.candidate_fingerprint != "0" * 64


# -- 2. provenance forgery --------------------------------------------

def test_cross_repair_artefact_mixing_refused():
    candidate, proposal, result, report, analysis = _fresh()
    _, other_proposal, _, _, _ = _fresh()
    other_proposal = dataclasses.replace(
        other_proposal, repair_id="repair-D-H-2"
    )
    _, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=other_proposal,
    )
    assert verdict.decision is AdmissionDecision.REJECTED


def test_swapped_validation_report_refused():
    candidate, proposal, result, report, analysis = _fresh()
    _, _, _, other_report, _ = _fresh()
    other_report = dataclasses.replace(
        other_report, validation_id="V-OTHER"
    )
    _, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=other_report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=proposal,
    )
    assert verdict.decision is AdmissionDecision.REJECTED


def test_failed_decision_with_accepted_provenance_refused():
    candidate, proposal, result, report, analysis = _fresh()
    failed = dataclasses.replace(result, decision=RepairDecision.FAILED)
    _, verdict = adjudicate(
        candidate=candidate,
        result=failed,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=proposal,
    )
    assert verdict.decision is AdmissionDecision.REJECTED


# -- 3. status bypass matrix -------------------------------------------

def test_status_transition_matrix_closed():
    candidate, *_ = _fresh()
    assert candidate.status is ContextStatus.CANDIDATE
    for target in (
        ContextStatus.ADMITTED,
        ContextStatus.SUPERSEDED,
    ):
        with pytest.raises(ValueError):
            candidate.with_status(target)
    for start, forbidden in (
        (ContextStatus.VALIDATED, ContextStatus.CANDIDATE),
        (ContextStatus.ADMITTED, ContextStatus.CANDIDATE),
        (ContextStatus.ADMITTED, ContextStatus.VALIDATED),
        (ContextStatus.ADMITTED, ContextStatus.REJECTED),
        (ContextStatus.REJECTED, ContextStatus.VALIDATED),
        (ContextStatus.REJECTED, ContextStatus.ADMITTED),
        (ContextStatus.SUPERSEDED, ContextStatus.ADMITTED),
    ):
        obj = dataclasses.replace(candidate, status=start)
        with pytest.raises(ValueError):
            obj.with_status(forbidden)
    with pytest.raises(ValueError):
        ContextStatus.from_str("APPROVED")


def test_gate_rejects_non_candidate_inputs():
    candidate, proposal, result, report, analysis = _fresh()
    store = MemoryStore(store_id="mem-1")
    for status in (
        ContextStatus.VALIDATED,
        ContextStatus.ADMITTED,
        ContextStatus.REJECTED,
    ):
        with pytest.raises(ValueError):
            adjudicate(
                candidate=dataclasses.replace(candidate, status=status),
                result=result,
                report=report,
                analysis=analysis,
                store=store,
                proposal=proposal,
            )


# -- 4. fault injection: weakened checks must turn tests red -----------

def test_weakened_acceptance_check_is_caught():
    # Simulates a refactor that accidentally drops the ACCEPTED-only
    # rule: the adversarial suite must contain a test pinning it.
    candidate, proposal, result, report, analysis = _fresh()
    failed = dataclasses.replace(result, decision=RepairDecision.FAILED)
    _, verdict = adjudicate(
        candidate=candidate,
        result=failed,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=proposal,
    )
    # If this ever returns ADMITTED, or rejects for any reason other
    # than the acceptance rule itself, the gate regressed: pin the
    # exact guard, not just the verdict.
    assert verdict.decision is AdmissionDecision.REJECTED
    assert "ACCEPTED" in verdict.reason


def test_weakened_linkage_check_is_caught():
    candidate, proposal, result, report, analysis = _fresh()
    tampered = dataclasses.replace(
        candidate,
        provenance={**dict(candidate.provenance),
                    "repair_fingerprint": "0" * 64},
    )
    _, verdict = adjudicate(
        candidate=tampered,
        result=result,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=proposal,
    )
    assert verdict.decision is AdmissionDecision.REJECTED


# -- 5. cross-process determinism --------------------------------------

_DETERMINISM_SCRIPT = (
    "from tests.context.test_extraction import _artefacts;"
    "from evaluation.context.extraction import extract_candidate;"
    "from evaluation.context.gate import adjudicate;"
    "from evaluation.context.memory import MemoryStore;"
    "proposal, result, report, analysis = _artefacts();"
    "candidate = extract_candidate(proposal=proposal, result=result,"
    " report=report, analysis=analysis);"
    "store = MemoryStore(store_id='mem-1');"
    "validated, verdict = adjudicate(candidate=candidate, result=result,"
    " report=report, analysis=analysis, store=store, proposal=proposal);"
    "stored = store.admit(validated, verdict);"
    "print(candidate.fingerprint());"
    "print(validated.fingerprint());"
    "print(stored.fingerprint());"
    "print(stored.store_version)"
)


def test_cross_process_determinism():
    def _run_once():
        import os

        package_root = str(
            pathlib.Path(__file__).resolve().parent.parent.parent
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = package_root + os.pathsep + env.get(
            "PYTHONPATH", ""
        )
        completed = subprocess.run(
            [sys.executable, "-c", _DETERMINISM_SCRIPT],
            capture_output=True,
            text=True,
            cwd=package_root,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        return completed.stdout.strip().splitlines()

    first, second = _run_once(), _run_once()
    assert first == second
    assert len(first) == 4


# -- 6. aliasing --------------------------------------------------------

def test_source_mutation_cannot_reach_store():
    candidate, proposal, result, report, analysis = _fresh()
    validated, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=MemoryStore(store_id="mem-1"),
        proposal=proposal,
    )
    stored = MemoryStore(store_id="mem-1").admit(validated, verdict)
    before = stored.to_dict()
    before_fp = stored.fingerprint()
    # Frozen mappings reject mutation outright; either way the
    # stored representation cannot be reached through aliases.
    with pytest.raises(TypeError):
        proposal.provenance["injected"] = True  # type: ignore[index]
    assert stored.to_dict() == before
    assert stored.fingerprint() == before_fp
    # Rebuilding equivalent sources reproduces the stored fingerprint.
    candidate2, _, _, _, _ = _fresh()
    assert candidate2.fingerprint() == candidate.fingerprint()


# -- 7/8. historical isolation + frozen boundary scans -----------------

def test_frozen_substrate_knows_no_e4_memory():
    root = (
        pathlib.Path(__file__).resolve().parent.parent.parent
    )
    scanned = []
    for relative in (
        "evaluation/contracts",
        "evaluation/baseline",
        "evaluation/diagnostics",
        "environment",
        "benchmarks",
    ):
        for path in sorted((root / relative).rglob("*.py")):
            text = path.read_text()
            scanned.append(str(path))
            for token in (
                "LearnedContext",
                "MemoryStore",
                "StoredEntry",
                "extract_candidate",
                "AdmissionVerdict",
            ):
                assert token not in text, f"{path} contains {token!r}"
    assert scanned


def test_no_adapt_calls_in_frozen_eval_paths():
    root = (
        pathlib.Path(__file__).resolve().parent.parent.parent
    )
    for relative in (
        "evaluation/diagnostics/repair",
        "evaluation/diagnostics/orchestration",
        "evaluation/baseline",
    ):
        for path in sorted((root / relative).rglob("*.py")):
            text = path.read_text()
            assert ".adapt(" not in text, f"{path} calls .adapt("


# -- 9. terminology scan ------------------------------------------------

# Tokens are assembled by concatenation so this file never literally
# contains a premature claim it is meant to forbid elsewhere.
_FORBIDDEN_CLAIMS = (
    "autonomous " + "learning",
    "self-" + "repair",
    "behaviour " + "b1",
    "behavior " + "b1",
    "proven " + "learning",
)
_NEGATION_MARKERS = (
    "no ", "not ", "never ", "without ", "do not", "n't ",
    "forbid", "refuse", "reject", "disclaimer", "bootstrap",
    "misconduct", "forgery", "smuggl",
)


def test_no_premature_learning_claims():
    root = (
        pathlib.Path(__file__).resolve().parent.parent.parent
    )
    offenders = []
    for relative in ("evaluation/context", "tests/context"):
        for path in sorted((root / relative).rglob("*.py")):
            if path.name == "test_adversarial.py":
                continue
            for lineno, line in enumerate(
                path.read_text().splitlines(), start=1
            ):
                lowered = line.lower()
                for token in _FORBIDDEN_CLAIMS:
                    if token in lowered and not any(
                        marker in lowered
                        for marker in _NEGATION_MARKERS
                    ):
                        offenders.append(
                            f"{path}:{lineno}: {token!r}"
                        )
    assert offenders == []
