"""E4-E controlled experiment tests: four-arm isolation, leakage lock.

Cheap only: no environment episodes. Heavy execution lives behind
``run_e4e`` and is not invoked here.
"""

import pathlib
import subprocess
import sys

import pytest

from benchmarks.volatility_threshold import VolatilityThresholdBenchmark
from evaluation.context.assembly import assemble, deliver
from evaluation.context.benchmark import (
    TURNOVER_MECHANISM,
    ContextualThresholdBenchmark,
)
from evaluation.context.experiment import (
    ARMS,
    COMPARISONS,
    E4EResult,
    TEMPORARY_PROVENANCE,
    apply_temporary,
    attest_leakage,
    build_temporary_payload,
    check_guards,
    check_window_order,
    collect_metric_map,
    compare_arms,
    e4e_result_path,
    execution_id,
    lock_c1,
    paired_delta,
    save_e4e_result,
    temporary_payload_fingerprint,
)
from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.memory import MemoryStore, StoredEntry
from evaluation.context.retrieval import retrieve
from evaluation.contracts.agent import AgentIdentity

from ..benchmarks.fixtures import make_obs


def _turnover_entry(**overrides):
    entry = {
        "context_id": "ctx-k1",
        "failure_mechanism": TURNOVER_MECHANISM,
        "corrective_principle": "throttle accumulation",
    }
    entry.update(overrides)
    return entry


def _context(context_id, agent_id="contextual-threshold-benchmark@1.0"):
    return LearnedContext(
        context_id=context_id,
        agent_id=agent_id,
        source_evaluation_id="E-diag",
        failure_mechanism="turnover",
        observed_pattern="p",
        triggering_conditions=("candidate_diagnostic",),
        diagnostic_evidence=("E-1",),
        corrective_principle="c",
        applicability_conditions=("candidate_diagnostic",),
        contraindications=(),
        expected_effect="e",
        validation_result="ACCEPTED",
        validation_metrics={},
        held_out_evidence={},
        provenance={"proposal_fingerprint": "p"},
        status=ContextStatus.ADMITTED,
        version="v1",
    )


def _admitted_store(*contexts):
    store = MemoryStore(store_id="mem-e4e")
    for index, context in enumerate(contexts):
        store = MemoryStore(
            store_id="mem-e4e",
            entries=store.entries + (
                StoredEntry(
                    entry_id=f"mem-{index}",
                    context=context,
                    verdict_fingerprint="vfp",
                    sequence=index + 1,
                    candidate_fingerprint=f"cfp-{index}",
                ),
            ),
        )
    return store


def _package_and_store():
    store = _admitted_store(_context("ctx-k1"))
    agent = ContextualThresholdBenchmark()
    identity = agent.identity
    contexts, record = retrieve(store, agent_id=str(identity))
    package = assemble(contexts, record, store.fingerprint(), identity)
    return package, store


def _result_kwargs(**overrides):
    arms = {
        arm: {
            "metrics": {"turnover": 1.0, "order_count": 4.0},
            "context": {"context": "C0"},
        }
        for arm in ARMS
    }
    kwargs = {
        "experiment_id": "e4e-test-001",
        "execution_role": "SYSTEM_VALIDATION",
        "execution_instance": "001",
        "protocol_fingerprint": "proto",
        "base_manifest_fingerprint": "base",
        "supplement_fingerprint": "supp",
        "amendment_fingerprint": "amend",
        "effective_manifest_fingerprint": "eff",
        "diagnostic_start": "2023-02-01",
        "diagnostic_end": "2023-02-28",
        "heldout_start": "2023-03-01",
        "heldout_end": "2023-03-31",
        "diagnostic_env_fingerprint": "diag-env",
        "heldout_env_fingerprint": "held-env",
        "agent_id": "contextual-threshold-benchmark",
        "agent_version": "1.0",
        "arms": arms,
        "lineage": {"proposal_fingerprint": "p"},
        "leakage": {
            "diagnostic_end": "2023-02-28",
            "heldout_start": "2023-03-01",
        },
    }
    kwargs.update(overrides)
    return kwargs


# 1. C0 is behaviourally identical to the frozen benchmark.
def test_c0_matches_frozen_benchmark():
    frozen = VolatilityThresholdBenchmark()
    fresh = ContextualThresholdBenchmark()
    for obs_kwargs in (
        {"vix": 12.5},
        {"vix": 20.0},
        {"vix": 30.0},
        {"vix": None},
    ):
        obs = make_obs(**obs_kwargs)
        assert fresh.act(dict(obs)) == frozen.act(dict(obs))


# 2. Arm C payload is explicitly provisional.
def test_temporary_payload_is_provisional():
    payload = build_temporary_payload([_turnover_entry()])
    assert payload["provisional"] is True
    assert payload["provenance"] == TEMPORARY_PROVENANCE
    assert temporary_payload_fingerprint(payload)
    with pytest.raises(ValueError):
        apply_temporary(
            ContextualThresholdBenchmark(),
            {"entries": payload["entries"]},
        )


# 3. Arm C creates no MemoryStore state.
def test_temporary_path_creates_no_store():
    store = _admitted_store(_context("ctx-k1"))
    before = store.fingerprint()
    payload = build_temporary_payload([_turnover_entry()])
    agent = ContextualThresholdBenchmark()
    apply_temporary(agent, payload)
    assert store.fingerprint() == before
    assert set(payload) == {"entries", "provisional", "provenance"}


# 4. Arm C creates no admission verdicts.
def test_temporary_payload_carries_no_verdict():
    payload = build_temporary_payload([_turnover_entry()])
    text = repr(payload)
    assert "AdmissionVerdict" not in text
    assert "verdict_fingerprint" not in text
    assert "candidate_fingerprint" not in text


# 5. Arm C creates no mem-* identifiers.
def test_temporary_payload_has_no_mem_ids():
    payload = build_temporary_payload([_turnover_entry()])
    assert "mem-" not in repr(payload)
    with pytest.raises(ValueError):
        build_temporary_payload(
            [_turnover_entry(context_id="mem-1")]
        )


# 6. Arm C cannot contaminate arm D lineage.
def test_temporary_copy_does_not_touch_store_or_original():
    from evaluation.diagnostics.repair.application import fingerprint_agent

    package, store = _package_and_store()
    store_fp = store.fingerprint()
    agent = ContextualThresholdBenchmark()
    agent_fp_before = fingerprint_agent(agent, agent.identity)
    payload = build_temporary_payload(
        [dict(entry) for entry in package.knowledge]
    )
    adapted = apply_temporary(agent, payload)
    assert adapted is not agent
    assert list(agent.learned_contexts) == []
    assert list(adapted.learned_contexts) != []
    assert store.fingerprint() == store_fp
    # Original agent is fingerprint-identical before and after: the
    # temporary delivery reached only the isolated copy.
    assert fingerprint_agent(agent, agent.identity) == agent_fp_before
    assert (
        fingerprint_agent(adapted, adapted.identity) != agent_fp_before
    )


# 7. Arm D requires valid store lineage.
def test_persistent_delivery_requires_live_store_lineage():
    package, store = _package_and_store()
    other = _admitted_store(_context("ctx-other"))
    agent = ContextualThresholdBenchmark()
    with pytest.raises(ValueError):
        deliver(agent, package, other)


# 8. Arm D cannot use hand-built context.
def test_hand_built_package_refused_at_delivery():
    package, store = _package_and_store()
    forged = package.to_dict()
    forged["knowledge"] = [
        {
            **dict(forged["knowledge"][0]),
            "context_id": "ctx-forged",
        }
    ]
    from evaluation.context.assembly import ContextPackage

    rebuilt = ContextPackage(
        agent_identity=package.agent_identity,
        store_fingerprint=package.store_fingerprint,
        retrieved_ids=package.retrieved_ids,
        knowledge=tuple(
            dict(item) for item in forged["knowledge"]
        ),
        retrieval_method=package.retrieval_method,
        retrieval_version=package.retrieval_version,
    )
    with pytest.raises(ValueError):
        deliver(ContextualThresholdBenchmark(), rebuilt, store)


# 9. C1 lock precedes held-out execution (attestation binds both).
def test_lock_attestation_binds_before_heldout():
    package, store = _package_and_store()
    lock = lock_c1(store, package)
    assert lock["store_fingerprint_at_lock"] == store.fingerprint()
    assert lock["package_fingerprint_at_lock"] == package.fingerprint()
    attestation = attest_leakage(
        diagnostic_end="2023-02-28",
        heldout_start="2023-03-01",
        lock=lock,
    )
    assert attestation["c1_locked_before_heldout"] is True
    assert attestation["temporal_order_ok"] is True


# 10. heldout_start must strictly exceed diagnostic_end.
def test_window_order_refuses_overlap_and_equality():
    check_window_order("2023-02-28", "2023-03-01")
    with pytest.raises(ValueError):
        check_window_order("2023-02-28", "2023-02-28")
    with pytest.raises(ValueError):
        check_window_order("2023-03-01", "2023-02-28")
    with pytest.raises(ValueError):
        attest_leakage(
            diagnostic_end="2023-03-01",
            heldout_start="2023-03-01",
            lock={
                "store_fingerprint_at_lock": "s",
                "package_fingerprint_at_lock": "p",
            },
        )


# 11. Metric collection preserves None (undefined is never zero).
def test_none_preservation_in_deltas():
    assert paired_delta({"t": None}, {"t": 1.0}) == {"t": None}
    assert paired_delta({"t": 2.0}, {"t": 1.0}) == {"t": -1.0}
    assert collect_metric_map({"a": None, "b": 2}) == {
        "a": None,
        "b": 2.0,
    }
    guards = check_guards(
        {"turnover": 2.0, "inactivity_rate": 0.0,
         "invalid_order_count": 0.0},
        {"turnover": None, "inactivity_rate": None,
         "invalid_order_count": None},
    )
    assert guards["any_guard"] is False


# 12. Arms receive fresh agent instances.
def test_fresh_instances_per_arm():
    agents = [ContextualThresholdBenchmark() for _ in ARMS]
    assert len({id(agent) for agent in agents}) == len(ARMS)
    payload = build_temporary_payload([_turnover_entry()])
    first = apply_temporary(agents[2], payload)
    assert first is not agents[2]
    assert list(agents[2].learned_contexts) == []


# 13. Artefacts live under results/e4 only.
def test_result_path_is_e4_only_and_no_overwrite(tmp_path):
    exec_id = execution_id("e4e-x", "SYSTEM_VALIDATION", "001")
    path = e4e_result_path(str(tmp_path), "e4e-x", exec_id)
    assert "/results/e4/" in path
    assert "/results/e3/" not in path
    result = E4EResult(**_result_kwargs(experiment_id="e4e-x"))
    saved = save_e4e_result(result, str(tmp_path))
    assert saved == path
    with pytest.raises(ValueError):
        save_e4e_result(result, str(tmp_path))


# 14. Deterministic E4EResult fingerprint.
def test_e4e_result_deterministic_fingerprint():
    first = E4EResult(**_result_kwargs())
    reordered = dict(reversed(list(_result_kwargs().items())))
    second = E4EResult(**reordered)
    assert first.fingerprint() == second.fingerprint()
    assert E4EResult.from_dict(first.to_dict()) == first
    with pytest.raises(ValueError):
        E4EResult.from_dict({**first.to_dict(), "surprise": 1})


# 15. Cross-process fingerprint stability.
def test_cross_process_fingerprint_stability():
    from evaluation.contracts.fingerprints import fingerprint_of_dict

    payload = {"b": [1, 2], "a": {"x": None, "y": 1.5}}
    local = fingerprint_of_dict(payload)
    code = (
        "import json;"
        "from evaluation.contracts.fingerprints import "
        "fingerprint_of_dict;"
        f"print(fingerprint_of_dict({payload!r}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=pathlib.Path(__file__).resolve().parent.parent.parent,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == local


# 16. E4-D boundaries remain intact.
def test_frozen_eval_paths_know_no_e4_memory():
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    frozen = (
        root / "evaluation" / "diagnostics" / "repair",
        root / "evaluation" / "diagnostics" / "orchestration",
        root / "evaluation" / "baseline",
    )
    texts = {}
    for directory in frozen:
        for path in sorted(directory.glob("*.py")):
            texts[f"{directory.name}/{path.name}"] = path.read_text()
    for name, text in texts.items():
        for token in (
            "LearnedContext",
            "MemoryStore",
            "evaluation.context.retrieval",
            "evaluation.context.assembly",
            "extract_candidate",
            "ContextPackage",
            ".adapt(",
        ):
            assert token not in text, f"{name} contains {token!r}"


# 17. E2-F repair paths stay adapt-free and context-free.
def test_repair_paths_have_no_adapt_or_context():
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    repair = root / "evaluation" / "diagnostics" / "repair"
    for path in sorted(repair.glob("*.py")):
        text = path.read_text()
        assert ".adapt(" not in text, f"{path.name} calls adapt"
        assert "evaluation.context" not in text, (
            f"{path.name} imports E4 context"
        )


# 18. Frozen E0-E3 paths import no E4 context.
def test_frozen_paths_import_no_e4():
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    frozen_dirs = (
        root / "evaluation" / "contracts",
        root / "evaluation" / "baseline",
        root / "evaluation" / "diagnostics",
        root / "benchmarks",
        root / "experiments" / "harness",
    )
    offenders = []
    for directory in frozen_dirs:
        for path in sorted(directory.rglob("*.py")):
            text = path.read_text()
            if "evaluation.context" in text or "evaluation/context" in text:
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


# 19. No evaluator routing from the E4-E runner.
def test_experiment_has_no_evaluator_routing():
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    text = (root / "evaluation" / "context" / "experiment.py").read_text()
    assert "evaluators" not in text
    assert "TripleAgent" not in text
    assert "rule-table" not in text


# 20. Only the three sanctioned adapt() call sites exist in E4:
# assembly (store-bound delivery), experiment (temporary arm C),
# cycles (dual-temporary arm T12).
def test_adapt_call_sites_remain_sanctioned():
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    context_dir = root / "evaluation" / "context"
    counts = {}
    for path in sorted(context_dir.glob("*.py")):
        counts[path.name] = path.read_text().count(".adapt(")
    assert counts.get("assembly.py") == 1
    assert counts.get("experiment.py") == 1
    assert counts.get("cycles.py") == 1
    for name, count in counts.items():
        if name not in ("assembly.py", "experiment.py", "cycles.py"):
            assert count == 0, f"{name} has {count} adapt callers"
    # comparisons cover exactly the four required pairs
    assert set(COMPARISONS) == {"A_vs_D", "A_vs_C", "C_vs_D", "B_vs_C"}
    assert set(ARMS) == {"A", "B", "C", "D"}


def test_comparisons_report_observed_direction():
    metrics = {
        "A": {"turnover": 2.0, "order_count": 4.0},
        "B": {"turnover": 2.0, "order_count": 4.0},
        "C": {"turnover": 1.0, "order_count": 3.0},
        "D": {"turnover": 1.0, "order_count": 2.0},
    }
    out = compare_arms(metrics)
    assert out["A_vs_D"]["turnover"] == -1.0
    assert out["C_vs_D"]["order_count"] == -1.0
    assert out["B_vs_C"]["turnover"] == -1.0
