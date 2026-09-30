"""M-R6 natural Indian-market adaptive repair (additive, terminal phase).

Pipeline (all pre-registered in configs/adaptive_repair/mr6_natural.yaml):
  BASE diagnostic run (frozen MultiAssetChoice, Indian env)
  -> adapt DecisionRecords (PIT-safe fields only)
  -> run all 5 detectors -> select (support/severity/lexical) or NULL
  -> FailureMechanism -> generate (diagnostic ONLY) -> compile all
  -> shadow all -> verify each via MemoryConditionedAgent serving
  -> adjudicate (frozen) -> FREEZE (held-out asserted absent)
  -> held-out runs (winner only) -> gates -> admission decision
  -> persistence + rollback (if admitted) -> replication (if admitted)
  -> artefacts + verdict.

Outcome-blind diagnosis: the adapter refuses retrospective legs
(forward/MAE/MFE/hold/opportunity/attribution); detectors consume only
decision-time or already-recorded state. No P&L-based mechanism
selection anywhere: multi_rule ranks support, then severity, then id.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys

sys.path.insert(0, ".")

import yaml

from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.context.extraction import extract_candidate
from evaluation.context.gate import adjudicate, AdmissionDecision
from evaluation.context.memory import MemoryStore
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.diagnostics.repair.provider import DeterministicRuleProvider
from evaluation.diagnostics.repair.regression import (
    ToleranceRule,
    analyze_regression,
)
from evaluation.diagnostics.repair.results import (
    RepairDecision,
    RepairResult,
    _decide,
)
from evaluation.diagnostics.repair.validation import (
    ValidationReport,
    ValidationRun,
)
from evaluation.repair import natural
from evaluation.repair.adaptive import (
    DETECTORS,
    CandidateEvaluation,
    adjudicate_candidates,
    generate_candidates,
)
from evaluation.repair.audit import AuditChain
from evaluation.repair.compiler import Uncompilable, compile_candidate
from evaluation.repair.gate import (
    assemble_verification,
    coverage_precheck,
    paired_bootstrap_ci,
)
from evaluation.repair.schemas import FailureMechanism, MemoryEntry
from evaluation.contracts.budget import EvaluationBudget

PROTOCOL_PATH = "configs/adaptive_repair/mr6_natural.yaml"
OUT_DIR = "data/adaptive_repair/M-R6"

KNOWN_STATUSES = ("VALIDATED",)


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _load_agent(protocol: dict):
    module_name, _, class_name = protocol["agent"]["module"].rpartition(".")
    module = importlib.import_module(module_name)
    with open(os.path.join(protocol["_base_dir"],
                           protocol["agent"]["config"])) as handle:
        policy = yaml.safe_load(handle)["policy"]
    return getattr(module, class_name)(policy)


def _build_config(protocol: dict, experiment_id: str, window: dict):
    env = protocol["environment"]
    return BaselineConfig(
        evaluation_id=experiment_id,
        start_date=window["start"],
        end_date=window["end"],
        universe={
            "nse_equity": list(env["universe"]["nse_equity"]),
            "mcx_gold": list(env["universe"]["mcx_gold"]),
        },
        transaction_cost_bps=float(env["transaction_cost_bps"]),
        initial_cash=float(env["initial_cash"]),
        strict_pit=bool(env["strict_pit"]),
        vintage_policy=str(env["vintage_policy"]),
        budget=EvaluationBudget(
            max_episodes=10, max_tests=None, max_repairs=None,
            max_validation_runs=None, max_runtime=None),
        seed=None)


def _trace_metrics(records):
    """Economics + validity from canonical records (no future legs)."""
    equities = []
    costs = 0.0
    violations = 0
    inactivity = 0
    for record in records:
        before = record.get("portfolio_before", {})
        after = record.get("portfolio_after", {})
        try:
            equities.append(float(after.get("total_equity",
                                            before.get("total_equity", 0.0))))
        except (TypeError, ValueError):
            continue
        try:
            costs += float(record.get("transaction_cost", 0.0))
        except (TypeError, ValueError):
            pass
        if not record.get("submitted_orders"):
            inactivity += 1
        for entry in record.get("validation", []) or []:
            status = str(entry.get("status", ""))
            if status != "VALIDATED" and not status.startswith("NOOP"):
                violations += 1
    peak = equities[0] if equities else 0.0
    max_drawdown = 0.0
    for value in equities:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    n = len(records)
    return {
        "final_value": equities[-1] if equities else 0.0,
        "initial_value": equities[0] if equities else 0.0,
        "max_drawdown": max_drawdown,
        "costs": costs,
        "inactivity_rate": inactivity / n if n else 1.0,
        "violations": violations,
        "n_sessions": n,
    }


def _block_values(sessions, normal_quantity, block_size):
    out = []
    for start in range(0, len(sessions), block_size):
        chunk = sessions[start:start + block_size]
        if not chunk:
            continue
        excess = sum(max(0.0, float(r.get("buy_quantity", 0.0) or 0.0)
                         - normal_quantity) for r in chunk)
        out.append({"start": start, "end": start + len(chunk) - 1,
                    "value": excess})
    return out


def run_mr6(base_dir: str, overwrite: bool = False) -> dict:
    protocol = dict(yaml.safe_load(
        open(os.path.join(base_dir, PROTOCOL_PATH))))
    protocol["_base_dir"] = base_dir
    exp = protocol["experiment_id"]
    out_dir = os.path.join(base_dir, OUT_DIR)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    if os.path.exists(out_dir) and overwrite:
        import shutil
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    chain = AuditChain()
    adj_cfg = protocol["adjudication"]
    stats_cfg = adj_cfg["bootstrap"]
    mech_cfg = protocol["mechanism_templates"]
    vix_map = natural.load_vix_map(base_dir)

    def write(name: str, payload) -> str:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        return path

    protocol_fp = _fingerprint(
        {k: v for k, v in protocol.items() if not k.startswith("_")})
    write("protocol.yaml", {k: v for k, v in protocol.items()
                            if not k.startswith("_")})
    chain.append("PROTOCOL_FROZEN", {"protocol_fingerprint": protocol_fp})

    # ---- BASE diagnostic run (frozen agent, Indian env) ----
    diag = protocol["windows"]["diagnostic"]
    agent = _load_agent(protocol)
    base_fp = fingerprint_agent(agent, agent.identity)
    base_result = run_baseline(
        _load_agent(protocol),
        _build_config(protocol, f"{exp}-base-diag", diag),
        base_dir=base_dir)
    base_records = [r.to_dict() for r in base_result.decision_records]
    write("base_diagnostic.json", {
        "records": base_records,
        "metrics": _trace_metrics(base_records)})
    chain.append("BASE_SEALED", {
        "policy_fingerprint": base_fp,
        "n_records": len(base_records)})
    sessions = natural.adapt_records(base_records, vix_map)
    write("diagnostic_sessions.json", sessions)

    # ---- Detect all five mechanisms; pre-registered selection ----
    detections = []
    for name in ("loss_chasing", "overtrading", "exposure", "volatility",
                 "drawdown"):
        params = dict(protocol["detection"]["detector_params"][name])
        fn = DETECTORS[name]
        if name == "volatility":
            vix_series = [s["vix"] if s["vix"] is not None else 0.0
                          for s in sessions]
            spec = fn(sessions, vix_series,
                      mechanism_id=f"{exp}-{name}", **params)
        else:
            spec = fn(sessions, mechanism_id=f"{exp}-{name}", **params)
        if spec is not None:
            detections.append(spec)
    write("detections.json", [{
        "mechanism_id": s.mechanism_id, "failure_type": s.failure_type,
        "support": s.support, "severity": s.severity,
        "evidence_refs": list(s.evidence_refs)} for s in detections])
    chain.append("DETECTED", {"count": len(detections)})
    if not detections:
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NULL",
                       reason="NATURAL-MARKET-NULL: no supported mechanism",
                       extra={"detections": []})
    detections.sort(key=lambda s: (-s.support, -s.severity,
                                   s.mechanism_id))
    mechanism = detections[0]
    chain.append("MECHANISM_SELECTED", {
        "mechanism_id": mechanism.mechanism_id,
        "rule": protocol["detection"]["multi_rule"]})

    # ---- Generate + compile (diagnostic ONLY) ----
    template = mech_cfg[mechanism.failure_type]
    failure_mech = FailureMechanism(
        mechanism_id=mechanism.mechanism_id,
        taxonomy=template["taxonomy"],
        condition=tuple(mechanism.evidence_refs),
        scope_hint=dict(template.get("scope_hint", {})),
        trigger_hint=tuple(tuple(t) for t in template.get("trigger_hint",
                                                           [])),
        evidence_refs=tuple(mechanism.evidence_refs),
        provenance={"protocol_fingerprint": protocol_fp,
                    "detector": mechanism.provenance.get("detector", "")},
    )
    generated = generate_candidates(mechanism, sessions, exp)
    compiled = []
    refused = []
    for gen in generated:
        spec = compile_candidate(
            failure_mech, gen.family, gen.params,
            spec_id=f"{exp}-spec-{gen.candidate_id}")
        if isinstance(spec, Uncompilable):
            refused.append({"candidate_id": gen.candidate_id,
                            "family": gen.family,
                            "reason": spec.reason})
        else:
            compiled.append((gen, spec))
    write("candidates.json", {
        "generated": [{"candidate_id": g.candidate_id, "family": g.family,
                       "params": dict(g.params)} for g in generated],
        "refused": refused})
    chain.append("GENERATED", {"n_generated": len(generated),
                               "n_compiled": len(compiled),
                               "n_refused": len(refused)})
    if not compiled:
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NULL",
                       reason="NATURAL-MARKET-REPAIR-NULL: nothing compilable",
                       extra={"refused": refused})

    # ---- Shadow + verify each candidate via serving path ----
    target_cfg = protocol["target"]
    block_size = int(target_cfg.get("block_size", 10))
    normal_qty = float(target_cfg.get("normal_quantity", 2.0))
    normal_bound = dict(protocol["normal_bound"])
    evaluations = []
    candidate_records = []
    rep_traces = {}
    winner_entries = {}
    for gen, spec in compiled:
        entry = MemoryEntry(
            entry_id=f"mem-{gen.candidate_id}",
            agent_id=agent.identity.agent_id,
            spec=spec,
            source_evaluation_id=f"{exp}-base-diag",
            diagnostic_evidence=(f"{exp}:natural",),
            provenance={"mechanism_fingerprint": failure_mech.fingerprint(),
                        "protocol_fingerprint": protocol_fp})
        shadow = MemoryConditionedAgent(
            _load_agent(protocol), [entry], (entry.entry_id,), shadow=True)
        shadow_result = run_baseline(
            shadow,
            _build_config(protocol, f"{exp}-shadow-{gen.candidate_id}",
                          diag),
            base_dir=base_dir)
        shadow_records = [r.to_dict()
                          for r in shadow_result.decision_records]
        assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in shadow_records] == \
               [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in base_records], \
            f"shadow diverged for {gen.candidate_id}"
        served = MemoryConditionedAgent(
            _load_agent(protocol), [entry], (entry.entry_id,))
        policy_ok = served.base_policy_fingerprint() == base_fp
        rep_result = run_baseline(
            served,
            _build_config(protocol, f"{exp}-rep-{gen.candidate_id}", diag),
            base_dir=base_dir)
        rep_records = [r.to_dict() for r in rep_result.decision_records]
        rep_traces[gen.candidate_id] = rep_records
        winner_entries[gen.candidate_id] = entry
        rep_sessions = natural.adapt_records(rep_records, vix_map)
        base_blocks = _block_values(sessions, normal_qty, block_size)
        rep_blocks = _block_values(rep_sessions, normal_qty, block_size)
        diffs = [r["value"] - b["value"]
                 for r, b in zip(rep_blocks, base_blocks)]
        ci = paired_bootstrap_ci(
            diffs, seed=stats_cfg["seed"], n_boot=stats_cfg["n_boot"],
            alpha=stats_cfg["alpha"])
        protected = natural.protected_mask(
            sessions, tuple(tuple(t) for t in template.get("trigger_hint",
                                                           [])),
            spec.rule_type, dict(spec.rule_params), normal_bound)
        base_orders = [json.dumps(r.get("submitted_orders", []),
                                  sort_keys=True) for r in base_records]
        rep_orders = [json.dumps(r.get("submitted_orders", []),
                                 sort_keys=True) for r in rep_records]
        normal_ok = all(b == r for b, r, keep
                        in zip(base_orders, rep_orders, protected) if keep)
        fires = sum(1 for b, r in zip(base_orders, rep_orders) if b != r)
        rep_metrics = _trace_metrics(rep_records)
        base_metrics = _trace_metrics(base_records)
        evaluations.append({
            "candidate_id": gen.candidate_id, "family": gen.family,
            "params": dict(gen.params),
            "spec_fingerprint": spec.fingerprint(),
            "target_reduction": sum(diffs) / len(diffs) if diffs else 0.0,
            "ci_lower": ci["lower"], "ci_upper": ci["upper"],
            "support": mechanism.support,
            "fires": fires,
            "suppression_rate": fires / len(base_records),
            "normal_preserved": bool(normal_ok),
            "final_value": rep_metrics["final_value"],
            "base_final_value": base_metrics["final_value"],
            "drawdown": rep_metrics["max_drawdown"],
            "base_drawdown": base_metrics["max_drawdown"],
            "inactivity": rep_metrics["inactivity_rate"],
            "base_inactivity": base_metrics["inactivity_rate"],
            "policy_ok": bool(policy_ok),
            "validity_ok": rep_metrics["violations"] == 0,
        })
        candidate_records.append({
            "candidate_id": gen.candidate_id, "family": gen.family,
            "params": dict(gen.params), "spec": spec.to_dict(),
            "entry_fingerprint": entry.fingerprint(),
            "target_reduction": evaluations[-1]["target_reduction"],
            "ci": {"lower": ci["lower"], "upper": ci["upper"]},
            "fires": fires})
    write("candidate_results.json", {"evaluations": evaluations})
    chain.append("EVALUATED", {"n": len(evaluations)})

    # ---- Adjudicate + FREEZE (held-out asserted absent) ----
    from evaluation.repair.adaptive import (
        CandidateEvaluation, adjudicate_candidates)
    adjudication = adjudicate_candidates(
        [CandidateEvaluation(**ev) for ev in evaluations],
        min_support=adj_cfg["min_support"],
        tolerance_value=adj_cfg["tolerance_value"],
        tolerance_drawdown=adj_cfg["tolerance_drawdown"])
    write("adjudication.json", {
        "ranked_ids": list(adjudication.ranked_ids),
        "selected_id": adjudication.selected_id,
        "reasons": {k: v for k, v in adjudication.reasons.items()},
        "rejected": list(adjudication.rejected)})
    write("freeze.json", {
        "selected_id": adjudication.selected_id,
        "spec_fingerprint": next(
            (c["spec_fingerprint"] for c in evaluations
             if c["candidate_id"] == adjudication.selected_id), ""),
        "protocol_fingerprint": protocol_fp})
    chain.append("FROZEN", {"selected": adjudication.selected_id})
    held_dir = os.path.join(base_dir, "data", "processed", "india")
    assert not os.path.exists(os.path.join(out_dir, "heldout.json")), \
        "held-out artefacts must not predate the freeze"
    _ = held_dir

    # ---- Held-out: winner ONLY ----
    held = protocol["windows"]["heldout"]
    if not adjudication.selected_id:
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NULL",
                       reason="NATURAL-MARKET-REPAIR-NULL: no admissible repair",
                       extra={"adjudication": "NO ADMISSIBLE REPAIR"})
    selected = next(c for c in candidate_records
                    if c["candidate_id"] == adjudication.selected_id)
    from evaluation.repair.schemas import RepairSpec
    from evaluation.repair.schemas import MemoryEntry as EntryCls
    selected_spec = RepairSpec.from_dict(selected["spec"])
    winner = EntryCls(
        entry_id=f"mem-{adjudication.selected_id}",
        agent_id=agent.identity.agent_id,
        spec=selected_spec,
        source_evaluation_id=f"{exp}-base-diag",
        diagnostic_evidence=(f"{exp}:natural",),
        provenance={"mechanism_fingerprint": failure_mech.fingerprint(),
                    "protocol_fingerprint": protocol_fp,
                    "candidate_id": adjudication.selected_id})
    served_held = MemoryConditionedAgent(
        _load_agent(protocol), [winner], (winner.entry_id,))
    base_held_result = run_baseline(
        _load_agent(protocol),
        _build_config(protocol, f"{exp}-base-held", held),
        base_dir=base_dir)
    rep_held_result = run_baseline(
        served_held,
        _build_config(protocol, f"{exp}-rep-held", held),
        base_dir=base_dir)
    base_held_records = [r.to_dict()
                         for r in base_held_result.decision_records]
    rep_held_records = [r.to_dict()
                        for r in rep_held_result.decision_records]
    base_held_sessions = natural.adapt_records(base_held_records, vix_map)
    rep_held_sessions = natural.adapt_records(rep_held_records, vix_map)
    base_hvals = _block_values(base_held_sessions, normal_qty, block_size)
    rep_hvals = _block_values(rep_held_sessions, normal_qty, block_size)
    held_diffs = [r["value"] - b["value"]
                  for r, b in zip(rep_hvals, base_hvals)]
    held_ci = paired_bootstrap_ci(
        held_diffs, seed=stats_cfg["seed"] + 1,
        n_boot=stats_cfg["n_boot"], alpha=stats_cfg["alpha"])
    held_target_ok = bool(
        held_diffs and sum(held_diffs) / len(held_diffs) < 0)
    rep_held_metrics = _trace_metrics(rep_held_records)
    base_held_metrics = _trace_metrics(base_held_records)
    held_econ_ok = bool(
        rep_held_metrics["final_value"] >= base_held_metrics["final_value"]
        * (1.0 - adj_cfg["tolerance_value"])
        and rep_held_metrics["max_drawdown"]
        <= base_held_metrics["max_drawdown"] + adj_cfg["tolerance_drawdown"])
    write("heldout.json", {
        "base": base_held_metrics, "repaired": rep_held_metrics,
        "held_ci": held_ci, "target_improved": held_target_ok,
        "economics_ok": held_econ_ok})
    chain.append("HELDOUT", {"target_improved": held_target_ok,
                             "economics_ok": held_econ_ok})
    admitted = bool(held_target_ok and held_econ_ok)
    result_payload = {
        "experiment": exp,
        "selected_id": adjudication.selected_id,
        "selected_family": selected["family"],
        "held_target_improved": held_target_ok,
        "held_economics_ok": held_econ_ok,
        "held_ci": held_ci,
        "policy_fingerprint": base_fp,
    }
    if not admitted:
        result_payload["persistence"] = "NOT_ATTEMPTED"
        result_payload["rollback"] = "NOT_ATTEMPTED"
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NULL",
                       reason="held-out gates failed: no admission",
                       extra=result_payload)

    # ---- Formal gate + admission through frozen path ----
    winner_rep = rep_traces[adjudication.selected_id]
    winner_entry = winner_entries[adjudication.selected_id]
    winner_diag_sessions = natural.adapt_records(winner_rep, vix_map)
    base_diag_blocks = _block_values(sessions, normal_qty, block_size)
    winner_diag_blocks = _block_values(
        winner_diag_sessions, normal_qty, block_size)
    comparisons = [
        ("candidate_diagnostic", "adaptive_target",
         _mean([b["value"] for b in base_diag_blocks]),
         _mean([b["value"] for b in winner_diag_blocks])),
    ]
    base_diag_metrics = _trace_metrics(base_records)
    winner_diag_metrics = _trace_metrics(winner_rep)
    for metric in ("final_portfolio_value", "max_drawdown_ratio",
                   "turnover", "inactivity_rate"):
        key = {"final_portfolio_value": "final_value",
               "max_drawdown_ratio": "max_drawdown",
               "turnover": "turnover",
               "inactivity_rate": "inactivity_rate"}[metric]
        comparisons.append(
            ("candidate_diagnostic", metric, base_diag_metrics[key],
             winner_diag_metrics[key]))
    base_held_metrics = _trace_metrics(base_held_records)
    rep_held_metrics = _trace_metrics(rep_held_records)
    for metric in ("final_portfolio_value", "max_drawdown_ratio",
                   "turnover", "inactivity_rate"):
        key = {"final_portfolio_value": "final_value",
               "max_drawdown_ratio": "max_drawdown",
               "turnover": "turnover",
               "inactivity_rate": "inactivity_rate"}[metric]
        comparisons.append(
            ("candidate_heldout", metric, base_held_metrics[key],
             rep_held_metrics[key]))
    analysis = analyze_regression(
        analysis_id=f"{exp}-analysis",
        candidate_id=adjudication.selected_id,
        validation_fingerprint="pending-report",
        comparisons=tuple(comparisons),
        tolerances=())
    provider = DeterministicRuleProvider()
    proposal = provider.propose(
        repair_id=f"{exp}-repair", diagnostic_id=f"{exp}-diagnosis",
        baseline_evaluation_id=f"{exp}-base-diag",
        baseline_fingerprint=_fingerprint(base_records),
        diagnostic_state_fingerprint=failure_mech.fingerprint(),
        target_agent_identity=agent.identity,
        target_agent_fingerprint=base_fp,
        hypothesis_id=failure_mech.mechanism_id,
        hypothesis_fingerprint=failure_mech.fingerprint(),
        failure_class=template["taxonomy"],
        evidence_refs=(mechanism.mechanism_id,))
    formal_metric = proposal.target_metric
    comparisons = comparisons + [
        ("candidate_diagnostic", formal_metric,
         _formal_metric_value(base_records, formal_metric),
         _formal_metric_value(winner_rep, formal_metric)),
        ("candidate_heldout", formal_metric,
         _formal_metric_value(base_held_records, formal_metric),
         _formal_metric_value(rep_held_records, formal_metric)),
    ]
    report = ValidationReport(
        validation_id=f"{exp}-validation",
        candidate_id=adjudication.selected_id,
        candidate_fingerprint=_fingerprint({"spec": selected["spec"]}),
        baseline_evaluation_id=f"{exp}-base-diag",
        baseline_fingerprint=_fingerprint(base_records),
        runs=(
            ValidationRun(
                label="candidate_diagnostic", window=("DIAG", "DIAG"),
                result_fingerprint=_fingerprint(winner_rep),
                metrics=_window_metrics(winner_rep)),
            ValidationRun(
                label="candidate_heldout", window=("HELD", "HELD"),
                result_fingerprint=_fingerprint(rep_held_records),
                metrics=_window_metrics(rep_held)),
            ValidationRun(
                label="original_heldout", window=("HELD", "HELD"),
                result_fingerprint=_fingerprint(base_held_records),
                metrics=_window_metrics(base_held)),
        ),
        method="control-plane", method_version="v1")
    analysis = analyze_regression(
        analysis_id=f"{exp}-analysis",
        candidate_id=adjudication.selected_id,
        validation_fingerprint=report.fingerprint(),
        comparisons=tuple(comparisons),
        tolerances=())
    decision, reason = _decide(
        report=report, analysis=analysis,
        target_metric=formal_metric,
        target_direction=ExpectedDirection.DECREASE)
    write("validation_report.json", report.to_dict())
    write("regression_analysis.json", analysis.to_dict())
    if decision != RepairDecision.ACCEPTED:
        result_payload["formal_decision"] = str(decision)
        result_payload["formal_reason"] = reason
        result_payload["persistence"] = "NOT_ATTEMPTED"
        result_payload["rollback"] = "NOT_ATTEMPTED"
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NULL",
                       reason=f"formal gate refused: {reason}",
                       extra=result_payload)
    result = RepairResult(
        repair_id=f"{exp}-repair",
        proposal_fingerprint=proposal.fingerprint(),
        candidate_id=adjudication.selected_id,
        candidate_fingerprint=_fingerprint({"spec": selected["spec"]}),
        validation_fingerprint=report.fingerprint(),
        analysis_fingerprint=analysis.fingerprint(),
        decision=RepairDecision.ACCEPTED, reason=reason,
        suggested_stopping=None, method="control-plane",
        method_version="v1")
    candidate_ctx = extract_candidate(
        proposal=proposal, result=result, report=report,
        analysis=analysis)
    store = MemoryStore(store_id=f"{exp}-store", entries=())
    validated, admission = adjudicate(
        candidate=candidate_ctx, result=result, report=report,
        analysis=analysis, store=store, proposal=proposal)
    if admission.decision is not AdmissionDecision.ADMITTED:
        result_payload["persistence"] = "NOT_ATTEMPTED"
        result_payload["rollback"] = "NOT_ATTEMPTED"
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NULL",
                       reason=f"admission refused: {admission}",
                       extra=result_payload)
    store = store.admit(validated, admission)
    chain.append("ADMITTED", {"store": store.fingerprint()})
    serving = MemoryEntry(
        entry_id=winner_entry.entry_id,
        agent_id=winner_entry.agent_id,
        spec=winner_entry.spec,
        source_evaluation_id=winner_entry.source_evaluation_id,
        diagnostic_evidence=winner_entry.diagnostic_evidence,
        priority=winner_entry.priority,
        sequence=winner_entry.sequence,
        provenance={**dict(winner_entry.provenance),
                    "candidate_fingerprint": validated.fingerprint(),
                    "store_fingerprint": store.fingerprint()})
    from evaluation.repair import control_plane
    assert control_plane.verify_admission(store, serving)
    write("memory_store.json", store.to_dict())
    write("serving_entry.json", serving.to_dict())
    result_payload["store_fingerprint"] = store.fingerprint()
    # Persistence round-trip.
    re_store = MemoryStore.from_dict(
        json.load(open(os.path.join(out_dir, "memory_store.json"))))
    re_entry = MemoryEntry.from_dict(
        json.load(open(os.path.join(out_dir, "serving_entry.json"))))
    assert re_store.fingerprint() == store.fingerprint()
    assert re_entry.fingerprint() == serving.fingerprint()
    re_served = MemoryConditionedAgent(
        _load_agent(protocol), [re_entry], (re_entry.entry_id,))
    re_result = run_baseline(
        re_served, _build_config(protocol, f"{exp}-persist", diag),
        base_dir=base_dir)
    re_records = [r.to_dict() for r in re_result.decision_records]
    assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in re_records] == \
           [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in winner_rep], \
        "reloaded repair must reproduce conditioned behaviour exactly"
    assert re_served.base_policy_fingerprint() == base_fp
    chain.append("PERSISTED", {"reproduced": True})
    result_payload["persistence"] = "REPRODUCED"
    # Rollback.
    rolled = MemoryConditionedAgent(
        _load_agent(protocol), [re_entry], ())
    roll_result = run_baseline(
        rolled, _build_config(protocol, f"{exp}-rollback", diag),
        base_dir=base_dir)
    roll_records = [r.to_dict() for r in roll_result.decision_records]
    assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in roll_records] == \
           [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in base_records], \
        "deactivation must restore base behaviour exactly"
    assert rolled.base_policy_fingerprint() == base_fp
    chain.append("ROLLED_BACK", {"restored": True})
    result_payload["rollback"] = "RESTORED"

    # ---- Replication (only on acceptance) ----
    rep_win = protocol["windows"]["replication"]
    rep_base_result = run_baseline(
        _load_agent(protocol),
        _build_config(protocol, f"{exp}-repl-base", rep_win),
        base_dir=base_dir)
    rep_base_records = [r.to_dict()
                        for r in rep_base_result.decision_records]
    rep_base_sessions = natural.adapt_records(rep_base_records, vix_map)
    high_action = sum(
        1 for s in rep_base_sessions
        if (s["vix"] or 0) > 25.0
        and (s["buy_quantity"] > 0 or s["sell_quantity"] > 0))
    gate = protocol["replication_support_gate"]["min_high_action_sessions"]
    replication: dict = {"window": rep_win, "high_action_sessions":
                         high_action, "gate": gate}
    if high_action < gate:
        replication["verdict"] = "NSF"
        replication["reason"] = "replication support gate failed"
    else:
        rep_served = MemoryConditionedAgent(
            _load_agent(protocol), [re_entry], (re_entry.entry_id,))
        rep_rep_result = run_baseline(
            rep_served,
            _build_config(protocol, f"{exp}-repl-rep", rep_win),
            base_dir=base_dir)
        rep_rep_records = [r.to_dict()
                           for r in rep_rep_result.decision_records]
        rep_rep_sessions = natural.adapt_records(rep_rep_records, vix_map)
        base_vals = _block_values(rep_base_sessions, normal_qty)
        rep_vals = _block_values(rep_rep_sessions, normal_qty)
        diffs = [r - b for r, b in zip(rep_vals, base_vals)]
        replication["mean_diff"] = sum(diffs) / len(diffs) if diffs else 0.0
        replication["verdict"] = ("REPLICATED"
                                  if diffs and replication["mean_diff"] < 0
                                  else "NOT-REPLICATED")
        assert rep_served.base_policy_fingerprint() == base_fp
    write("replication.json", replication)
    chain.append("REPLICATED", {"verdict": replication["verdict"]})
    result_payload["replication"] = replication
    return _finish(out_dir, write, chain, protocol, protocol_fp,
                   base_fp, verdict="SUCCESS",
                   reason="natural adaptive repair admitted and verified",
                   extra=result_payload)


def _block_values(sessions, normal_quantity, block_size=10):
    out = []
    for start in range(0, len(sessions), block_size):
        chunk = sessions[start:start + block_size]
        if not chunk:
            continue
        excess = sum(max(0.0, float(r.get("buy_quantity", 0.0) or 0.0)
                         - normal_quantity) for r in chunk)
        out.append({"start": start, "end": start + len(chunk) - 1,
                    "value": excess})
    return out


def _formal_metric_value(records, metric_name):
    sessions = [r for r in records]
    if metric_name == "max_post_loss_quantity":
        best, prev_neg = 0.0, False
        for row in sessions:
            if not isinstance(row, dict):
                continue
            qty = sum(float(o.get("quantity", 0.0))
                      for o in row.get("submitted_orders", [])
                      if isinstance(o, dict) and o.get("side") == "BUY")
            if prev_neg:
                best = max(best, qty)
            try:
                prev_neg = float(row.get("reward", 0.0)) < 0.0
            except (TypeError, ValueError):
                prev_neg = False
        return best
    if metric_name == "turnover":
        total = 0.0
        for row in sessions:
            try:
                total += float(row.get("transaction_cost", 0.0))
            except (TypeError, ValueError):
                continue
        return total
    if metric_name == "gross_exposure_max":
        peak = 0.0
        for row in sessions:
            before = row.get("portfolio_before", {})
            if isinstance(before, dict):
                try:
                    peak = max(peak, float(before.get("exposure", 0.0)))
                except (TypeError, ValueError):
                    continue
        return peak
    return None


def _window_metrics(records):
    metrics = _trace_metrics(records)
    return {
        "final_portfolio_value": metrics["final_value"],
        "max_drawdown_ratio": metrics["max_drawdown"],
        "turnover": metrics["turnover"],
        "inactivity_rate": metrics["inactivity_rate"],
    }


def _finish(out_dir, write, chain, protocol, protocol_fp, base_fp,
            verdict, reason, extra):
    payload = {"experiment": protocol["experiment_id"], "verdict": verdict,
               "reason": reason, "policy_fingerprint": base_fp,
               "protocol_fingerprint": protocol_fp, **extra}
    write("result.json", payload)
    write("audit.json", chain.to_list())
    manifest = {"experiment": protocol["experiment_id"],
                "label": protocol.get("label", ""),
                "verdict": verdict,
                "protocol_fingerprint": protocol_fp,
                "policy_fingerprint": base_fp}
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    print(f"{protocol['experiment_id']}: verdict={verdict} reason={reason}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="M-R6 natural repair")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run_mr6(args.base_dir, args.overwrite)


if __name__ == "__main__":
    main()
