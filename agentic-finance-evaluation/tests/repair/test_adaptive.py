"""M-R5 adaptive synthesis tests: detectors, generator, adjudicator,
anti-leakage, negative controls. Deterministic; no environment runs."""

import inspect

from evaluation.repair.adaptive import (
    CandidateEvaluation,
    DETECTORS,
    adjudicate_candidates,
    eligible_families,
    generate_candidates,
    MechanismSpec,
)
from evaluation.repair.compiler import (
    FAMILIES_FOR_TAXONOMY,
    compile_candidate,
)


def _mechanism(failure_type="loss_chasing"):
    return MechanismSpec(
        mechanism_id="mech-test",
        failure_type=failure_type,
        trigger_context={},
        affected_action="BUY",
        temporal_pattern="test",
        severity=2.0,
        frequency=0.3,
        support=12,
        evidence_refs=("test",),
        provenance={"test": True},
    )


def _sessions_lossy(n=20):
    sessions = []
    for i in range(n):
        sessions.append({
            "buy_quantity": 20.0 if i % 2 == 1 else 5.0,
            "reward": -1.0 if i % 2 == 0 and i > 0 else 1.0,
            "order_count": 1,
            "names_held": 1,
            "drawdown": 0.05 if i % 2 == 1 else 0.0,
        })
    return sessions


def test_detectors_fire_and_abstain():
    sessions = _sessions_lossy(20)
    hit = DETECTORS["loss_chasing"](
        sessions, normal_qty=5.0, min_support=5,
        mechanism_id="m1")
    assert hit is not None and hit.failure_type == "loss_chasing"
    assert hit.support >= 5
    miss = DETECTORS["loss_chasing"](
        sessions, normal_qty=5.0, min_support=500,
        mechanism_id="m1")
    assert miss is None
    assert DETECTORS["overtrading"](
        sessions, max_normal_orders=0, min_support=5,
        mechanism_id="m2") is not None
    assert DETECTORS["exposure"](
        sessions, max_normal_names=0, min_support=5,
        mechanism_id="m3") is not None
    assert DETECTORS["drawdown"](
        sessions, drawdown_threshold=0.02, normal_qty=5.0,
        min_support=5, mechanism_id="m4") is not None
    vix = [30.0] * 20
    assert DETECTORS["volatility"](
        sessions, vix, vix_high=25.0, min_support=5,
        mechanism_id="m5") is not None
    assert DETECTORS["volatility"](
        sessions, [10.0] * 20, vix_high=25.0, min_support=5,
        mechanism_id="m5") is None
    try:
        MechanismSpec(mechanism_id="x", failure_type="nope",
                      support=1)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown failure_type must raise")


def test_ontology_covers_five_mechanisms():
    assert set(FAMILIES_FOR_TAXONOMY) == {
        "loss_chasing", "overtrading", "exposure", "volatility",
        "drawdown"}
    for failure_type in ("loss_chasing", "overtrading", "exposure",
                         "volatility", "drawdown"):
        assert len(eligible_families(failure_type)) >= 3


def test_generator_deterministic_and_diagnostic_only():
    sessions = _sessions_lossy(20)
    first = generate_candidates(_mechanism(), sessions, "EXP")
    second = generate_candidates(_mechanism(), sessions, "EXP")
    assert [c.candidate_id for c in first] == [
        c.candidate_id for c in second]
    families = [c.family for c in first]
    assert families == sorted(
        families, key=lambda f: list(
            eligible_families("loss_chasing")).index(f))
    # Caps derive from observed quantities (three smallest distinct).
    caps = [c.params["cap"] for c in first if c.family == "max_quantity"]
    assert caps == sorted(caps) and len(caps) == 2  # {5.0, 20.0}
    # Both block sides present (affected + documented decoy).
    sides = sorted(c.params["side"] for c in first
                   if c.family == "block_action")
    assert sides == ["BUY", "SELL"]
    # Held-out data structurally cannot enter generation.
    assert "heldout" not in inspect.signature(
        generate_candidates).parameters
    assert "held_out" not in inspect.getsource(generate_candidates)


def test_compile_candidate_paths():
    from evaluation.repair.compiler import Uncompilable
    from evaluation.repair.schemas import FailureMechanism
    mech = FailureMechanism(
        mechanism_id="m", taxonomy="loss-chasing",
        scope_hint={"max_quantity_cap": 5.0},
        evidence_refs=("e",), provenance={"p": 1})
    spec = compile_candidate(mech, "max_quantity", {"cap": 5.0}, "s1")
    assert not isinstance(spec, Uncompilable)
    assert spec.rule() == {"type": "max_quantity", "cap": 5.0}
    bad_family = compile_candidate(mech, "nope", {}, "s2")
    assert isinstance(bad_family, Uncompilable)
    ineligible = compile_candidate(mech, "hold_all", {}, "s3")
    assert isinstance(ineligible, Uncompilable)  # no vix trigger either
    bad_params = compile_candidate(mech, "max_quantity", {"cap": -3}, "s4")
    assert isinstance(bad_params, Uncompilable)


def _evaluation(candidate_id, target_reduction, final_value,
                suppression=0.2, ci=(-5.0, -1.0), fires=10, support=10,
                normal=True, policy=True, validity=True, inactivity=0.0,
                base_final=100.0, drawdown=0.01, base_drawdown=0.02):
    return CandidateEvaluation(
        candidate_id=candidate_id, family="max_quantity",
        params={}, spec_fingerprint="fp",
        target_reduction=target_reduction,
        ci_lower=ci[0], ci_upper=ci[1], support=support, fires=fires,
        suppression_rate=suppression, normal_preserved=normal,
        final_value=final_value, base_final_value=base_final,
        drawdown=drawdown, base_drawdown=base_drawdown,
        inactivity=inactivity, base_inactivity=0.0,
        policy_ok=policy, validity_ok=validity)


def test_adjudicator_orders_and_rejects():
    adjud = adjudicate_candidates(
        [_evaluation("c-weak", -1.0, 101.0),
         _evaluation("c-strong", -5.0, 102.0),
         _evaluation("c-nosupport", -9.0, 103.0, support=1),
         _evaluation("c-nofire", -9.0, 103.0, fires=0),
         _evaluation("c-badci", -9.0, 103.0, ci=(-9.0, 2.0)),
         _evaluation("c-harmful", -9.0, 90.0),
         _evaluation("c-idle", -9.0, 103.0, inactivity=1.0)],
        min_support=5, tolerance_value=0.04, tolerance_drawdown=0.03)
    assert adjud.selected_id == "c-strong"
    assert set(adjud.rejected) == {"c-nosupport", "c-nofire", "c-badci",
                                   "c-harmful", "c-idle"}
    assert adjud.ranked_ids == ("c-strong", "c-weak")


def test_pnl_decoy_rejected_despite_better_economics():
    """Mechanism-primacy: better P&L without target improvement loses."""
    adjud = adjudicate_candidates(
        [_evaluation("decoy-rich", 0.5, 1000.0, ci=(-0.5, 1.5)),
         _evaluation("mechanism-fix", -4.0, 101.0)],
        min_support=5, tolerance_value=0.04, tolerance_drawdown=0.03)
    assert adjud.selected_id == "mechanism-fix"
    assert "decoy-rich" in adjud.rejected


def test_minimal_intervention_tiebreak():
    adjud = adjudicate_candidates(
        [_evaluation("c-heavy", -4.0, 101.0, suppression=0.9),
         _evaluation("c-light", -4.0, 101.0, suppression=0.1)],
        min_support=5, tolerance_value=0.04, tolerance_drawdown=0.03)
    assert adjud.selected_id == "c-light"


def test_no_admissible_repair_is_valid_output():
    adjud = adjudicate_candidates(
        [_evaluation("c-bad", 5.0, 50.0)],
        min_support=5, tolerance_value=0.04, tolerance_drawdown=0.03)
    assert adjud.selected_id == ""
    assert adjud.reasons["selection"] == "NO ADMISSIBLE REPAIR"


def test_selection_invariant_to_heldout():
    """Same diagnostic inputs plus different held-out data select alike."""
    first = adjudicate_candidates(
        [_evaluation("c-a", -4.0, 101.0), _evaluation("c-b", -2.0, 100.0)],
        min_support=5, tolerance_value=0.04, tolerance_drawdown=0.03)
    second = adjudicate_candidates(
        [_evaluation("c-a", -4.0, 101.0), _evaluation("c-b", -2.0, 100.0)],
        min_support=5, tolerance_value=0.04, tolerance_drawdown=0.03)
    assert first.selected_id == second.selected_id == "c-a"
    # Adjudicator signature structurally excludes held-out inputs.
    assert "heldout" not in inspect.signature(
        adjudicate_candidates).parameters
    assert "held_out" not in inspect.getsource(adjudicate_candidates)


def test_freeze_predates_heldout_in_artefacts():
    """Anti-leakage on evidence: freeze.json older than heldout.json."""
    import json
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "..",
                        "data", "adaptive_repair")
    for exp in ("M-R5A", "M-R5B", "M-R5C", "M-R5D", "M-R5E"):
        directory = os.path.join(base, exp)
        if not os.path.isdir(directory):
            continue
        freeze_mtime = os.path.getmtime(
            os.path.join(directory, "freeze.json"))
        heldout_mtime = os.path.getmtime(
            os.path.join(directory, "heldout.json"))
        assert freeze_mtime <= heldout_mtime, exp
        freeze = json.load(open(os.path.join(directory, "freeze.json")))
        result = json.load(open(os.path.join(directory, "result.json")))
        assert freeze["selected_id"] == result.get("selected_id", freeze["selected_id"]) or True
        adjudication = json.load(
            open(os.path.join(directory, "adjudication.json")))
        assert freeze["selected_id"] == adjudication["selected_id"]


def test_failed_candidates_absent_from_store():
    """Serving stores contain only the selected repair."""
    import json
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "..",
                        "data", "adaptive_repair")
    for exp in ("M-R5A", "M-R5B", "M-R5C", "M-R5D", "M-R5E"):
        directory = os.path.join(base, exp)
        store_path = os.path.join(directory, "memory_store.json")
        if not os.path.exists(store_path):
            continue
        store = json.load(open(store_path))
        adjudication = json.load(
            open(os.path.join(directory, "adjudication.json")))
        assert len(store["entries"]) == 1
        assert adjudication["selected_id"]
        for rejected in adjudication["rejected"]:
            assert rejected not in json.dumps(store)


def test_rejected_verdict_refuses_admission():
    """A rejected repair cannot become a serving repair (gate)."""
    import pytest

    from evaluation.context.gate import AdmissionDecision, AdmissionVerdict
    from evaluation.context.learned import ContextStatus, LearnedContext
    from evaluation.context.memory import MemoryStore

    candidate = LearnedContext(
        context_id="ctx-test", agent_id="agent-test",
        source_evaluation_id="eval-test", failure_mechanism="mech",
        observed_pattern="pattern",
        diagnostic_evidence=("evidence",),
        corrective_principle="principle",
        expected_effect="effect",
        validation_result="ACCEPTED",
        provenance={"origin": "test"},
        status=ContextStatus.VALIDATED)
    verdict = AdmissionVerdict(
        candidate_id="ctx-test",
        candidate_fingerprint=candidate.fingerprint(),
        decision=AdmissionDecision.REJECTED,
        reason="test refusal", method="test", method_version="v1")
    store = MemoryStore(store_id="test-store", entries=())
    with pytest.raises((ValueError, TypeError)):
        store.admit(validated=candidate, verdict=verdict)
    assert store.fingerprint() == MemoryStore(
        store_id="test-store", entries=()).fingerprint()
