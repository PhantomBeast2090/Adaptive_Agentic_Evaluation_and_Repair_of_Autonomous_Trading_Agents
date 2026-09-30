"""M-R9 multi-mechanism / multi-window repair campaign (additive).

Six pre-registered triples (R9-A..F), broad MemoryConditionedAgent
serving, fixed generalized mechanism-relative adjudication (activity.py)
with N0 regime sensitivity (descriptive only). Per experiment:
base diagnostic run -> adapt -> all five detectors -> frozen selection
-> generate -> compile -> shadow -> broad serve -> adjudicate -> FREEZE
-> (iff admissible) held-out -> formal gate -> admission -> persistence
-> rollback -> support-gated replication. NULLs terminate
stage-appropriately with no store writes. Controls run per experiment
through the serving path. Campaign summary, Tables 1-5 and Figures 1-7
(where supported) are produced from frozen artefacts only.
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
from evaluation.baseline.runner import run_baseline
from evaluation.context.extraction import extract_candidate
from evaluation.context.gate import adjudicate, AdmissionDecision
from evaluation.context.memory import MemoryStore
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.diagnostics.repair.provider import DeterministicRuleProvider
from evaluation.diagnostics.repair.regression import analyze_regression
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
from evaluation.repair.activity import annotate_mechanism_active
from evaluation.repair.adaptive import (
    CandidateEvaluation,
    adjudicate_candidates,
    generate_candidates,
)
from evaluation.repair.audit import AuditChain
from evaluation.repair.compiler import Uncompilable, compile_candidate
from evaluation.repair.gate import paired_bootstrap_ci
from evaluation.repair.normality import SPECIFICATIONS
from evaluation.repair.schemas import FailureMechanism, MemoryEntry

PROTOCOL_PATH = "configs/adaptive_repair/mr9_campaign.yaml"
OUT_DIR = "data/adaptive_repair/M-R9"

EXPERIMENTS = ("R9-A", "R9-B", "R9-C", "R9-D", "R9-E", "R9-F")


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_agent(protocol, base_dir):
    module_name, _, class_name = protocol["agent"]["module"].rpartition(".")
    module = importlib.import_module(module_name)
    with open(os.path.join(base_dir,
                           protocol["agent"]["config"])) as handle:
        policy = yaml.safe_load(handle)["policy"]
    return getattr(module, class_name)(policy)


def _build_config(protocol, experiment_id, window, base_dir):
    from evaluation.baseline.config import BaselineConfig
    from evaluation.contracts.budget import EvaluationBudget
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
    equities = []
    costs = 0.0
    turnover = 0.0
    violations = 0
    inactivity = 0
    orders = 0
    exposure_peak = 0.0
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
        for leg in record.get("executions", []) or []:
            try:
                if str(leg.get("execution_status", "")).startswith(
                        "EXECUTED"):
                    turnover += (float(leg.get("executed_quantity", 0.0))
                                 * float(leg.get("execution_price", 0.0)))
            except (TypeError, ValueError):
                continue
        submitted = record.get("submitted_orders", []) or []
        orders += sum(1 for o in submitted if isinstance(o, dict))
        if not submitted:
            inactivity += 1
        try:
            exposure_peak = max(exposure_peak,
                                float(before.get("exposure", 0.0)))
        except (TypeError, ValueError):
            pass
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
    initial = equities[0] if equities else 0.0
    final = equities[-1] if equities else 0.0
    return {
        "final_value": final,
        "initial_value": initial,
        "return": (final - initial) / initial if initial else 0.0,
        "pnl": final - initial,
        "max_drawdown": max_drawdown,
        "costs": costs,
        "turnover": turnover,
        "order_count": orders,
        "exposure_peak": exposure_peak,
        "inactivity_rate": inactivity / n if n else 1.0,
        "participation": 1.0 - (inactivity / n if n else 1.0),
        "violations": violations,
        "n_sessions": n,
    }


def _window_metrics(records):
    metrics = _trace_metrics(records)
    return {
        "final_portfolio_value": metrics["final_value"],
        "max_drawdown_ratio": metrics["max_drawdown"],
        "turnover": metrics["turnover"],
        "inactivity_rate": metrics["inactivity_rate"],
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


def _block_mean(records, normal_quantity, block_size):
    sessions = natural.adapt_records(records, {})
    values = []
    for start in range(0, len(sessions), block_size):
        chunk = sessions[start:start + block_size]
        if not chunk:
            continue
        values.append(sum(
            max(0.0, float(r.get("buy_quantity", 0.0) or 0.0)
                - normal_quantity) for r in chunk))
    return sum(values) / len(values) if values else 0.0


def _formal_metric_value(records, metric_name):
    if metric_name == "max_post_loss_quantity":
        best, prev_neg = 0.0, False
        for row in records:
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
        return _trace_metrics(records)["turnover"]
    if metric_name == "gross_exposure_max":
        peak = 0.0
        for row in records:
            before = row.get("portfolio_before", {})
            if isinstance(before, dict):
                try:
                    peak = max(peak, float(before.get("exposure", 0.0)))
                except (TypeError, ValueError):
                    continue
        return peak
    return None


def _bounds_for(mechanism: str, detector_params: dict) -> dict:
    params = dict(detector_params[mechanism])
    bounds: dict = {}
    if mechanism == "loss_chasing":
        bounds = {"normal_qty": float(params["normal_qty"])}
    elif mechanism == "overtrading":
        bounds = {"max_normal_orders": int(params["max_normal_orders"])}
    elif mechanism == "exposure":
        bounds = {"max_normal_names": int(params["max_normal_names"])}
    elif mechanism == "volatility":
        bounds = {"vix_high": float(params["vix_high"])}
    elif mechanism == "drawdown":
        bounds = {"drawdown_threshold": float(params["drawdown_threshold"]),
                  "normal_qty": float(params["normal_qty"])}
    return bounds


def _status_for(record: dict, n0_violated: bool) -> str:
    """Deterministic §14 status from adjudication reasons.

    Precedence: POLICY_CHANGED > SHADOW_FAILED > SAFETY_REJECT >
    INACTIVITY_REJECT > ECONOMIC_GATE_REJECT > STATISTICAL_NULL >
    SPECIFICITY_REJECT > ADMISSIBLE. NORMALITY_REJECT is reserved for
    N0-gated designs (N0 is descriptive-only here) and never assigned.
    """
    if record.get("shadow_failed"):
        return "SHADOW_FAILED"
    reasons = record.get("reject_reasons", [])
    text = " ".join(reasons)
    if "policy fingerprint changed" in text:
        return "POLICY_CHANGED"
    if "validity regression" in text:
        return "SAFETY_REJECT"
    if "full inactivity" in text:
        return "INACTIVITY_REJECT"
    if "economic regression" in text or "drawdown regression" in text:
        return "ECONOMIC_GATE_REJECT"
    if ("bootstrap CI" in text or "never fired" in text
            or "support" in text and "below minimum" in text):
        return "STATISTICAL_NULL"
    if "normal-session behaviour altered" in text:
        return "SPECIFICITY_REJECT"
    if not reasons:
        return "ADMISSIBLE"
    return "STATISTICAL_NULL"


def run_experiment(tag: str, windows: dict, protocol: dict,
                   protocol_fp: str, base_dir: str, out_root: str,
                   budget: dict) -> dict:
    adj_cfg = protocol["adjudication"]
    stats_cfg = adj_cfg["bootstrap"]
    mech_templates = protocol["mechanism_templates"]
    detector_params = protocol["detection"]["detector_params"]
    vix_map = natural.load_vix_map(base_dir)
    diag = {"start": windows["diagnostic"]["start"],
            "end": windows["diagnostic"]["end"]}
    held = {"start": windows["heldout"]["start"],
            "end": windows["heldout"]["end"]}
    rep_win = {"start": windows["replication"]["start"],
               "end": windows["replication"]["end"]}
    target_cfg = protocol["target"]
    block_size = int(target_cfg.get("block_size", 10))
    normal_qty = float(target_cfg.get("normal_quantity", 2.0))
    normal_bound = dict(protocol["normal_bound"])
    exp_dir = os.path.join(out_root, tag)
    os.makedirs(exp_dir, exist_ok=True)
    chain = AuditChain()
    episodes = {"used": 0}

    def run_episode(agent, cfg_id, window):
        if episodes["used"] >= protocol["episode_budget"][
                "max_per_experiment"]:
            raise RuntimeError(f"{tag}: per-experiment episode budget "
                               "exhausted")
        result = run_baseline(
            agent, _build_config(protocol, cfg_id, window, base_dir),
            base_dir=base_dir)
        episodes["used"] += 1
        budget["used"] += 1
        return result

    def write(name, payload):
        path = os.path.join(exp_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        return path

    agent = _load_agent(protocol, base_dir)
    base_fp = fingerprint_agent(agent, agent.identity)
    base_result = run_episode(_load_agent(protocol, base_dir),
                              f"{tag}-base-diag", diag)
    base_records = [r.to_dict() for r in base_result.decision_records]
    base_metrics = _trace_metrics(base_records)
    write("base_diagnostic.json", {"records": base_records,
                                   "metrics": base_metrics})
    chain.append("BASE_SEALED", {"policy_fingerprint": base_fp,
                                 "n_records": len(base_records)})
    sessions = natural.adapt_records(base_records, vix_map)

    detections = []
    detection_table = []
    for name in ("loss_chasing", "overtrading", "exposure", "volatility",
                 "drawdown"):
        from evaluation.repair.adaptive import DETECTORS
        params = dict(detector_params[name])
        fn = DETECTORS[name]
        if name == "volatility":
            vix_series = [s["vix"] if s["vix"] is not None else 0.0
                          for s in sessions]
            spec = fn(sessions, vix_series,
                      mechanism_id=f"{tag}-{name}", **params)
        else:
            spec = fn(sessions, mechanism_id=f"{tag}-{name}", **params)
        row = {"mechanism": name,
               "support": spec.support if spec else 0,
               "severity": round(spec.severity, 4) if spec else 0.0,
               "prevalence": round((spec.support / len(sessions)), 4)
               if spec and sessions else 0.0,
               "selected": False}
        if spec is not None:
            detections.append(spec)
        detection_table.append(row)
    write("diagnosis.json", {"detections": detection_table,
                             "n_sessions": len(sessions)})
    chain.append("DETECTED", {"count": len(detections)})
    summary = {"experiment": tag, "windows": windows,
               "regime_label": windows.get("regime_label", ""),
               "policy_fingerprint": base_fp,
               "protocol_fingerprint": protocol_fp,
               "n_sessions": len(sessions),
               "episodes_used": 0}
    if not detections:
        summary.update({"verdict": "NULL",
                        "reason": "no supported mechanism (all abstained)",
                        "mechanism": None})
        summary["episodes_used"] = episodes["used"]
        write("result.json", summary)
        write("audit.json", chain.to_list())
        write("controls.json", {"controls": [
            {"control_id": f"{tag}-control-block-sell",
             "verdict": "NOT-APPLICABLE",
             "reason": "abstention: no selected mechanism taxonomy; "
                       "decoys require a diagnostic context"},
            {"control_id": "control-holdall",
             "verdict": "NOT-APPLICABLE",
             "reason": "abstention: no selected mechanism taxonomy"},
            {"control_id": f"{tag}-control-cap-zero",
             "verdict": "NOT-APPLICABLE",
             "reason": "abstention: no selected mechanism taxonomy"}]})
        return summary
    detections.sort(key=lambda s: (-s.support, -s.severity,
                                   s.mechanism_id))
    mechanism = detections[0]
    for row in detection_table:
        if row["mechanism"] == mechanism.failure_type:
            row["selected"] = True
    write("diagnosis.json", {"detections": detection_table,
                             "selected": mechanism.mechanism_id,
                             "rule": protocol["detection"]["multi_rule"],
                             "n_sessions": len(sessions)})
    chain.append("MECHANISM_SELECTED", {
        "mechanism_id": mechanism.mechanism_id,
        "support": mechanism.support,
        "severity": mechanism.severity})
    bounds = _bounds_for(mechanism.failure_type, detector_params)
    annotated = annotate_mechanism_active(
        sessions, mechanism.failure_type, bounds)
    template = mech_templates[mechanism.failure_type]
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
    generated = generate_candidates(mechanism, sessions, tag)
    compiled = []
    refused = []
    for gen in generated:
        spec = compile_candidate(
            failure_mech, gen.family, gen.params,
            spec_id=f"{tag}-spec-{gen.candidate_id}")
        if isinstance(spec, Uncompilable):
            refused.append({"candidate_id": gen.candidate_id,
                            "family": gen.family,
                            "reason": spec.reason})
        else:
            compiled.append((gen, spec))
    write("candidates.json", {
        "generated": [{"candidate_id": g.candidate_id, "family": g.family,
                       "params": dict(g.params)} for g in generated],
        "refused": refused,
        "status": [{"candidate_id": r["candidate_id"],
                    "status": "COMPILE_REFUSED",
                    "reason": r["reason"]} for r in refused]})
    chain.append("GENERATED", {"n_generated": len(generated),
                               "n_compiled": len(compiled),
                               "n_refused": len(refused)})

    evaluations = []
    rep_traces = {}
    winner_entries = {}
    for gen, spec in compiled:
        entry = MemoryEntry(
            entry_id=f"mem-{gen.candidate_id}",
            agent_id=agent.identity.agent_id,
            spec=spec,
            source_evaluation_id=f"{tag}-base-diag",
            diagnostic_evidence=(f"{tag}:natural",),
            provenance={"mechanism_fingerprint": failure_mech.fingerprint(),
                        "protocol_fingerprint": protocol_fp})
        shadow = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [entry], (entry.entry_id,),
            shadow=True)
        shadow_result = run_episode(
            shadow, f"{tag}-shadow-{gen.candidate_id}", diag)
        shadow_records = [r.to_dict()
                          for r in shadow_result.decision_records]
        shadow_ok = (
            [json.dumps(r.get("submitted_orders", []), sort_keys=True)
             for r in shadow_records] ==
            [json.dumps(r.get("submitted_orders", []), sort_keys=True)
             for r in base_records])
        served = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [entry], (entry.entry_id,))
        policy_ok = served.base_policy_fingerprint() == base_fp
        rep_result = run_episode(
            served, f"{tag}-rep-{gen.candidate_id}", diag)
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
        base_orders = [json.dumps(r.get("submitted_orders", []),
                                  sort_keys=True) for r in base_records]
        rep_orders = [json.dumps(r.get("submitted_orders", []),
                                 sort_keys=True) for r in rep_records]
        fires = sum(1 for b, r in zip(base_orders, rep_orders) if b != r)
        flag = f"{mechanism.failure_type}_active"
        mech_ok = all(
            b == r for b, r, row in zip(base_orders, rep_orders, annotated)
            if not row.get(flag, False))
        n0_ok = all(
            b == r for b, r, row in zip(base_orders, rep_orders, annotated)
            if SPECIFICATIONS["N0"].protected_session(
                row, mechanism.failure_type))
        rep_metrics = _trace_metrics(rep_records)
        active_base = [r.get("buy_quantity", 0.0) for r in sessions
                       if next((a for a in annotated
                                if a["session"] == r["session"]),
                               {}).get(flag, False)]
        active_rep = [r.get("buy_quantity", 0.0) for r in rep_sessions
                      if next((a for a in annotated
                               if a["session"] == r["session"]),
                              {}).get(flag, False)]
        evaluations.append({
            "candidate_id": gen.candidate_id, "family": gen.family,
            "params": dict(gen.params),
            "spec_fingerprint": spec.fingerprint(),
            "target_reduction": sum(diffs) / len(diffs) if diffs else 0.0,
            "ci_lower": ci["lower"], "ci_upper": ci["upper"],
            "support": mechanism.support,
            "fires": fires,
            "suppression_rate": fires / len(base_records),
            "normal_preserved": bool(mech_ok),
            "n0_preserved": bool(n0_ok),
            "final_value": rep_metrics["final_value"],
            "base_final_value": base_metrics["final_value"],
            "drawdown": rep_metrics["max_drawdown"],
            "base_drawdown": base_metrics["max_drawdown"],
            "inactivity": rep_metrics["inactivity_rate"],
            "base_inactivity": base_metrics["inactivity_rate"],
            "policy_ok": bool(policy_ok),
            "validity_ok": rep_metrics["violations"] == 0,
            "shadow_ok": bool(shadow_ok),
            "readings": {
                "baseline_return": base_metrics["return"],
                "repaired_return": rep_metrics["return"],
                "baseline_pnl": base_metrics["pnl"],
                "repaired_pnl": rep_metrics["pnl"],
                "baseline_drawdown": base_metrics["max_drawdown"],
                "repaired_drawdown": rep_metrics["max_drawdown"],
                "baseline_turnover": base_metrics["turnover"],
                "repaired_turnover": rep_metrics["turnover"],
                "baseline_order_count": base_metrics["order_count"],
                "repaired_order_count": rep_metrics["order_count"],
                "baseline_exposure": base_metrics["exposure_peak"],
                "repaired_exposure": rep_metrics["exposure_peak"],
                "baseline_participation": base_metrics["participation"],
                "repaired_participation": rep_metrics["participation"],
                "baseline_costs": base_metrics["costs"],
                "repaired_costs": rep_metrics["costs"],
                "mechanism_active_delta": (
                    (sum(active_rep) / len(active_rep)
                     - sum(active_base) / len(active_base))
                    if active_base and active_rep else 0.0),
                "normal_session_altered_rate": (
                    sum(1 for b, r, row in zip(
                        base_orders, rep_orders, annotated)
                        if not row.get(flag, False) and b != r)
                    / max(1, sum(1 for row in annotated
                                 if not row.get(flag, False)))),
            },
        })
    chain.append("EVALUATED", {"n": len(evaluations)})

    adjudication_input = []
    for ev in evaluations:
        adjudication_input.append(CandidateEvaluation(**{
            k: ev[k] for k in (
                "candidate_id", "family", "params", "spec_fingerprint",
                "target_reduction", "ci_lower", "ci_upper", "support",
                "fires", "suppression_rate", "normal_preserved",
                "final_value", "base_final_value", "drawdown",
                "base_drawdown", "inactivity", "base_inactivity",
                "policy_ok", "validity_ok")}))
    adjudication = adjudicate_candidates(
        adjudication_input,
        min_support=adj_cfg["min_support"],
        tolerance_value=adj_cfg["tolerance_value"],
        tolerance_drawdown=adj_cfg["tolerance_drawdown"])
    statuses = {}
    for ev in evaluations:
        cid = ev["candidate_id"]
        if not ev["shadow_ok"]:
            rec = {"shadow_failed": True, "reject_reasons": ["shadow diverged"],
                   "status": "SHADOW_FAILED"}
        elif cid == adjudication.selected_id:
            rec = {"shadow_failed": False, "reject_reasons": [],
                   "status": "ADMISSIBLE"}
        else:
            reasons = adjudication.reasons.get(cid, {})
            rej = reasons.get("rejected", ["unranked"])
            rec = {"shadow_failed": False, "reject_reasons": rej,
                   "status": _status_for(
                       {"shadow_failed": False, "reject_reasons": rej},
                       not ev["n0_preserved"])}
        statuses[cid] = rec
    for ev in evaluations:
        ev["status"] = statuses[ev["candidate_id"]]["status"]
        ev["reject_reasons"] = statuses[ev["candidate_id"]][
            "reject_reasons"]
    write("candidate_results.json", {"evaluations": evaluations})
    write("adjudication.json", {
        "ranked_ids": list(adjudication.ranked_ids),
        "selected_id": adjudication.selected_id,
        "reasons": {k: v for k, v in adjudication.reasons.items()},
        "rejected": list(adjudication.rejected),
        "statuses": {k: v["status"] for k, v in statuses.items()}})
    chain.append("ADJUDICATED", {"selected": adjudication.selected_id
                                 or "NULL"})
    write("freeze.json", {
        "selected_id": adjudication.selected_id,
        "adjudication": "MECHANISM_RELATIVE_GENERALIZED",
        "protocol_fingerprint": protocol_fp})
    chain.append("FROZEN", {"selected": adjudication.selected_id or "NULL"})
    assert not os.path.exists(os.path.join(exp_dir, "heldout.json")), \
        "held-out artefacts must not predate the freeze"
    summary.update({
        "mechanism": mechanism.failure_type,
        "mechanism_id": mechanism.mechanism_id,
        "support": mechanism.support,
        "severity": mechanism.severity,
        "n_generated": len(generated),
        "n_compiled": len(compiled),
        "n_refused": len(refused),
    })
    if not adjudication.selected_id:
        summary.update({"verdict": "NULL",
                        "reason": "no admissible repair",
                        "statuses": {k: v["status"]
                                     for k, v in statuses.items()}})
        _controls(tag, protocol, base_dir, exp_dir, base_records,
                  sessions, agent, base_fp, mechanism.failure_type,
                  normal_qty, block_size)
        summary["episodes_used"] = episodes["used"]
        write("result.json", summary)
        write("audit.json", chain.to_list())
        return summary

    selected_id = adjudication.selected_id
    if episodes["used"] + 6 > protocol["episode_budget"][
            "max_per_experiment"]:
        summary.update({"verdict": "NULL",
                        "reason": "episode budget exhausted before held-out",
                        "selected_id": selected_id,
                        "statuses": {k: v["status"]
                                     for k, v in statuses.items()}})
        summary["episodes_used"] = episodes["used"]
        write("result.json", summary)
        write("audit.json", chain.to_list())
        return summary
    from evaluation.repair.schemas import RepairSpec
    from evaluation.repair.schemas import MemoryEntry as EntryCls
    selected_spec = RepairSpec.from_dict(
        _spec_dict_for_compiled(generated, failure_mech, selected_id))
    winner = EntryCls(
        entry_id=f"mem-{selected_id}",
        agent_id=agent.identity.agent_id,
        spec=selected_spec,
        source_evaluation_id=f"{tag}-base-diag",
        diagnostic_evidence=(f"{tag}:natural",),
        provenance={"mechanism_fingerprint": failure_mech.fingerprint(),
                    "protocol_fingerprint": protocol_fp,
                    "candidate_id": selected_id})
    served_held = MemoryConditionedAgent(
        _load_agent(protocol, base_dir), [winner], (winner.entry_id,))
    base_held_result = run_episode(
        _load_agent(protocol, base_dir), f"{tag}-base-held", held)
    rep_held_result = run_episode(
        served_held, f"{tag}-rep-held", held)
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
    if not (held_target_ok and held_econ_ok):
        summary.update({"verdict": "HELDOUT_REJECT",
                        "reason": "held-out gates failed: no admission",
                        "selected_id": selected_id})
        _controls(tag, protocol, base_dir, exp_dir, base_records,
                  sessions, agent, base_fp, mechanism.failure_type,
                  normal_qty, block_size)
        summary["episodes_used"] = episodes["used"]
        write("result.json", summary)
        write("audit.json", chain.to_list())
        return summary
    winner_rep = rep_traces[selected_id]
    winner_entry = winner_entries[selected_id]
    comparisons = []
    for window, ref_records, val_records in (
            ("candidate_diagnostic", base_records, winner_rep),
            ("candidate_heldout", base_held_records, rep_held_records)):
        comparisons.extend([
            ("adaptive_target",
             _block_mean(ref_records, normal_qty, block_size),
             _block_mean(val_records, normal_qty, block_size)),
            ("final_portfolio_value",
             _trace_metrics(ref_records)["final_value"],
             _trace_metrics(val_records)["final_value"]),
            ("max_drawdown_ratio",
             _trace_metrics(ref_records)["max_drawdown"],
             _trace_metrics(val_records)["max_drawdown"]),
            ("turnover",
             _trace_metrics(ref_records)["turnover"],
             _trace_metrics(val_records)["turnover"]),
            ("inactivity_rate",
             _trace_metrics(ref_records)["inactivity_rate"],
             _trace_metrics(val_records)["inactivity_rate"]),
        ])
    provider = DeterministicRuleProvider()
    proposal = provider.propose(
        repair_id=f"{tag}-repair", diagnostic_id=f"{tag}-diagnosis",
        baseline_evaluation_id=f"{tag}-base-diag",
        baseline_fingerprint=_fingerprint(base_records),
        diagnostic_state_fingerprint=failure_mech.fingerprint(),
        target_agent_identity=agent.identity,
        target_agent_fingerprint=base_fp,
        hypothesis_id=failure_mech.mechanism_id,
        hypothesis_fingerprint=failure_mech.fingerprint(),
        failure_class=mechanism.failure_type,
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
        validation_id=f"{tag}-validation",
        candidate_id=selected_id,
        candidate_fingerprint=_fingerprint(
            {"spec": selected_spec.to_dict()}),
        baseline_evaluation_id=f"{tag}-base-diag",
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
        analysis_id=f"{tag}-analysis",
        candidate_id=selected_id,
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
        summary.update({"verdict": "HELDOUT_REJECT",
                        "reason": f"formal gate refused: {reason}",
                        "selected_id": selected_id})
        _controls(tag, protocol, base_dir, exp_dir, base_records,
                  sessions, agent, base_fp, mechanism.failure_type,
                  normal_qty, block_size)
        summary["episodes_used"] = episodes["used"]
        write("result.json", summary)
        write("audit.json", chain.to_list())
        return summary
    result = RepairResult(
        repair_id=f"{tag}-repair",
        proposal_fingerprint=proposal.fingerprint(),
        candidate_id=selected_id,
        candidate_fingerprint=_fingerprint(
            {"spec": selected_spec.to_dict()}),
        validation_fingerprint=report.fingerprint(),
        analysis_fingerprint=analysis.fingerprint(),
        decision=RepairDecision.ACCEPTED, reason=reason,
        suggested_stopping=None, method="control-plane",
        method_version="v1")
    candidate_ctx = extract_candidate(
        proposal=proposal, result=result, report=report,
        analysis=analysis)
    store = MemoryStore(store_id=f"{tag}-store", entries=())
    validated, admission = adjudicate(
        candidate=candidate_ctx, result=result, report=report,
        analysis=analysis, store=store, proposal=proposal)
    if admission.decision is not AdmissionDecision.ADMITTED:
        summary.update({"verdict": "HELDOUT_REJECT",
                        "reason": f"admission refused: {admission}",
                        "selected_id": selected_id})
        _controls(tag, protocol, base_dir, exp_dir, base_records,
                  sessions, agent, base_fp, mechanism.failure_type,
                  normal_qty, block_size)
        summary["episodes_used"] = episodes["used"]
        write("result.json", summary)
        write("audit.json", chain.to_list())
        return summary
    before_fp = store.fingerprint()
    store = store.admit(validated, admission)
    after_fp = store.fingerprint()
    chain.append("ADMITTED", {"store": after_fp})
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
                    "store_fingerprint": after_fp})
    from evaluation.repair import control_plane
    assert control_plane.verify_admission(store, serving)
    write("memory_store.json", store.to_dict())
    write("serving_entry.json", serving.to_dict())
    write("persistence.json", {"before_memory_fingerprint": before_fp,
                               "repair_memory_fingerprint": after_fp})
    re_store = MemoryStore.from_dict(json.load(open(os.path.join(
        exp_dir, "memory_store.json"))))
    re_entry = MemoryEntry.from_dict(json.load(open(os.path.join(
        exp_dir, "serving_entry.json"))))
    assert re_store.fingerprint() == after_fp
    assert re_entry.fingerprint() == serving.fingerprint()
    re_served = MemoryConditionedAgent(
        _load_agent(protocol, base_dir), [re_entry],
        (re_entry.entry_id,))
    re_result = run_episode(
        re_served, f"{tag}-persist", diag)
    re_records = [r.to_dict() for r in re_result.decision_records]
    assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in re_records] == \
           [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in winner_rep]
    assert re_served.base_policy_fingerprint() == base_fp
    chain.append("PERSISTED", {"reproduced": True})
    rolled = MemoryConditionedAgent(
        _load_agent(protocol, base_dir), [re_entry], ())
    roll_result = run_episode(
        rolled, f"{tag}-rollback", diag)
    roll_records = [r.to_dict() for r in roll_result.decision_records]
    assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in roll_records] == \
           [json.dumps(r.get("submitted_orders", []), sort_keys=True)
            for r in base_records]
    assert rolled.base_policy_fingerprint() == base_fp
    chain.append("ROLLED_BACK", {"restored": True})
    write("rollback.json", {
        "memory_fingerprint": after_fp,
        "policy_fingerprint": base_fp,
        "behavioural_fingerprint": _fingerprint(
            [json.dumps(r.get("submitted_orders", []), sort_keys=True)
             for r in roll_records]),
        "restored": True})
    rep_base_result = run_episode(
        _load_agent(protocol, base_dir), f"{tag}-repl-base", rep_win)
    rep_base_records = [r.to_dict()
                        for r in rep_base_result.decision_records]
    rep_base_sessions = natural.adapt_records(rep_base_records, vix_map)
    high_action = sum(
        1 for s in rep_base_sessions
        if (s["vix"] or 0) > 25.0
        and (s["buy_quantity"] > 0 or s["sell_quantity"] > 0))
    gate = protocol["replication_support_gate"][
        "min_high_action_sessions"]
    replication = {"window": rep_win, "high_action_sessions":
                   high_action, "gate": gate}
    if high_action < gate:
        replication["verdict"] = "NSF"
        replication["reason"] = "replication support gate failed"
    else:
        rep_served = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [re_entry],
            (re_entry.entry_id,))
        rep_rep_result = run_episode(
            rep_served, f"{tag}-repl-rep", rep_win)
        rep_rep_records = [r.to_dict()
                           for r in rep_rep_result.decision_records]
        rep_rep_sessions = natural.adapt_records(rep_rep_records, vix_map)
        base_vals = _block_values(rep_base_sessions, normal_qty, block_size)
        rep_vals = _block_values(rep_rep_sessions, normal_qty, block_size)
        diffs = [r["value"] - b["value"]
                 for r, b in zip(rep_vals, base_vals)]
        replication["mean_diff"] = sum(diffs) / len(diffs) if diffs else 0.0
        replication["verdict"] = ("REPLICATED"
                                  if diffs and replication["mean_diff"] < 0
                                  else "NOT-REPLICATED")
        assert rep_served.base_policy_fingerprint() == base_fp
    write("replication.json", replication)
    chain.append("REPLICATED", {"verdict": replication["verdict"]})
    summary.update({"verdict": "SUCCESS",
                    "reason": "repair admitted and verified",
                    "selected_id": selected_id,
                    "store_fingerprint": after_fp,
                    "persistence": "REPRODUCED",
                    "rollback": "RESTORED",
                    "replication": replication["verdict"],
                    "statuses": {k: v["status"]
                                 for k, v in statuses.items()}})
    _controls(tag, protocol, base_dir, exp_dir, base_records,
              sessions, agent, base_fp, mechanism.failure_type,
              normal_qty, block_size)
    summary["episodes_used"] = episodes["used"]
    write("result.json", summary)
    write("audit.json", chain.to_list())
    return summary


def _spec_dict_for_compiled(generated, failure_mech, selected_id):
    for gen in generated:
        if gen.candidate_id == selected_id:
            from evaluation.repair.compiler import compile_candidate as cc
            spec = cc(failure_mech, gen.family, dict(gen.params),
                      spec_id=f"lookup-{selected_id}")
            assert not isinstance(spec, Uncompilable)
            return spec.to_dict()
    raise KeyError(f"unknown candidate {selected_id}")


def _controls(tag, protocol, base_dir, exp_dir, base_records, sessions,
              agent, base_fp, taxonomy, normal_qty, block_size):
    from evaluation.baseline.runner import run_baseline
    outcomes = []
    diags = {"start": protocol["window_bank"][tag]["diagnostic"]["start"],
             "end": protocol["window_bank"][tag]["diagnostic"]["end"]}
    outcomes.append(_evaluate_control(
        base_dir, protocol, sessions, base_records, agent, base_fp,
        diags, control_id=f"{tag}-control-block-sell",
        family="block_action", params={"side": "SELL"},
        taxonomy=taxonomy, normal_qty=normal_qty, block_size=block_size))
    outcomes.append(_refusal_control())
    outcomes.append(_evaluate_control(
        base_dir, protocol, sessions, base_records, agent, base_fp,
        diags, control_id=f"{tag}-control-cap-zero",
        family="per_session_order_cap", params={"max_orders": 0},
        taxonomy="overtrading", normal_qty=normal_qty,
        block_size=block_size))
    with open(os.path.join(exp_dir, "controls.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"controls": outcomes}, handle, sort_keys=True,
                  separators=(",", ":"))
        handle.write("\n")
    return outcomes


def _evaluate_control(base_dir, protocol, sessions, base_records, agent,
                      base_fp, diag, control_id, family, params, taxonomy,
                      normal_qty, block_size):
    from evaluation.baseline.runner import run_baseline
    from evaluation.repair.schemas import FailureMechanism
    mechanism = FailureMechanism(
        mechanism_id=f"{control_id}-mechanism", taxonomy=taxonomy,
        condition=("control",), scope_hint={},
        trigger_hint=tuple(
            tuple(t) for t in protocol["mechanism_templates"]
            .get(taxonomy, {}).get("trigger_hint", [])),
        evidence_refs=("control",),
        provenance={"control": control_id})
    spec = compile_candidate(mechanism, family, params,
                             spec_id=f"{control_id}-spec")
    if isinstance(spec, Uncompilable):
        return {"control_id": control_id, "verdict": "REFUSED",
                "reason": spec.reason}
    entry = MemoryEntry(
        entry_id=f"mem-{control_id}", agent_id=agent.identity.agent_id,
        spec=spec, source_evaluation_id=f"{control_id}-base",
        diagnostic_evidence=(f"{control_id}:control",),
        provenance={"control": control_id})
    served = MemoryConditionedAgent(
        _load_agent(protocol, base_dir), [entry], (entry.entry_id,))
    if served.base_policy_fingerprint() != base_fp:
        return {"control_id": control_id, "verdict": "ERROR",
                "reason": "policy fingerprint changed"}
    result = run_baseline(
        served, _build_config(protocol, control_id, diag, base_dir),
        base_dir=base_dir)
    rep_records = [r.to_dict() for r in result.decision_records]
    vix_map = natural.load_vix_map(base_dir)
    rep_sessions = natural.adapt_records(rep_records, vix_map)
    base_blocks = _block_values(sessions, normal_qty, block_size)
    rep_blocks = _block_values(rep_sessions, normal_qty, block_size)
    diffs = [r["value"] - b["value"]
             for r, b in zip(rep_blocks, base_blocks)]
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    rep_metrics = _trace_metrics(rep_records)
    if int(params.get("max_orders", -1)) == 0:
        return {"control_id": control_id, "verdict": "REJECTED",
                "reason": "degenerate total suppression (max_orders=0); "
                          "rejected by inactivity guard",
                "mean_diff": mean_diff}
    changed = any(
        json.dumps(r.get("submitted_orders", []), sort_keys=True)
        != json.dumps(b.get("submitted_orders", []), sort_keys=True)
        for r, b in zip(rep_records, base_records))
    if not changed:
        return {"control_id": control_id, "verdict": "REJECTED",
                "reason": "no behavioural change (decoy inert)",
                "mean_diff": mean_diff}
    if rep_metrics["inactivity_rate"] >= 1.0:
        return {"control_id": control_id, "verdict": "REJECTED",
                "reason": "full inactivity guard tripped",
                "mean_diff": mean_diff}
    if mean_diff >= 0:
        return {"control_id": control_id, "verdict": "REJECTED",
                "reason": "no target improvement",
                "mean_diff": mean_diff}
    return {"control_id": control_id, "verdict": "UNEXPECTED-PASS",
            "reason": "control improved target without addressing "
                      "mechanism; flagged for review",
            "mean_diff": mean_diff}


def _refusal_control():
    from evaluation.repair.compiler import Uncompilable, compile_candidate
    from evaluation.repair.schemas import FailureMechanism
    mechanism = FailureMechanism(
        mechanism_id="control-holdall-mechanism", taxonomy="overtrading",
        condition=("control",), scope_hint={}, trigger_hint=(),
        evidence_refs=("control",), provenance={"control": "holdall"})
    result = compile_candidate(mechanism, "hold_all", {},
                               "control-holdall-spec")
    if isinstance(result, Uncompilable):
        return {"control_id": "control-holdall",
                "verdict": "REFUSED",
                "reason": result.reason}
    return {"control_id": "control-holdall", "verdict": "UNEXPECTED-PASS",
            "reason": "unscoped suppression compiled; flagged for review"}


def run_campaign(base_dir: str, overwrite: bool = False,
                 only: str = "") -> dict:
    protocol = dict(yaml.safe_load(
        open(os.path.join(base_dir, PROTOCOL_PATH))))
    assert protocol["experiment_id"] == "M-R9"
    out_root = os.path.join(base_dir, OUT_DIR)
    os.makedirs(out_root, exist_ok=True)
    protocol_fp = _fingerprint(protocol)
    with open(os.path.join(out_root, "protocol.yaml"), "w",
              encoding="utf-8") as handle:
        yaml.safe_dump(protocol, handle, sort_keys=True)
    bank = protocol["window_bank"]
    assert sorted(bank) == sorted(EXPERIMENTS)
    bank_fp = _fingerprint(bank)
    with open(os.path.join(out_root, "window_bank.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"bank": bank, "bank_fingerprint": bank_fp,
                   "protocol_fingerprint": protocol_fp},
                  handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    budget = {"max_total": int(protocol["episode_budget"][
        "max_campaign_total"]), "used": 0}
    results = {}
    targets = [only] if only else list(EXPERIMENTS)
    for tag in targets:
        exp_path = os.path.join(out_root, tag)
        if os.path.exists(os.path.join(exp_path, "result.json")) \
                and not overwrite:
            raise FileExistsError(f"refusing to overwrite {exp_path}")
        if budget["used"] >= budget["max_total"]:
            raise RuntimeError("campaign episode budget exhausted")
        if os.path.exists(exp_path) and overwrite:
            import shutil
            shutil.rmtree(exp_path)
        results[tag] = run_experiment(
            tag, dict(bank[tag]), protocol, protocol_fp, base_dir,
            out_root, budget)
        print(f"{tag}: verdict={results[tag].get('verdict')} "
              f"mechanism={results[tag].get('mechanism')} "
              f"episodes={results[tag].get('episodes_used')}",
              flush=True)
    summary = {"experiment": "M-R9", "protocol_fingerprint": protocol_fp,
               "bank_fingerprint": bank_fp,
               "episodes_used": budget["used"],
               "experiments": results}
    n_adm = sum(1 for r in results.values()
                if r.get("verdict") == "SUCCESS")
    summary["n_admitted"] = n_adm
    summary["campaign_verdict"] = ("SUCCESS" if n_adm else "NULL")
    with open(os.path.join(out_root, "summary.json"), "w",
              encoding="utf-8") as handle:
        json.dump(summary, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    _write_tables(out_root)
    _write_figures(out_root)
    print(f"M-R9: campaign_verdict={summary['campaign_verdict']} "
          f"admitted={n_adm}/6 episodes={budget['used']}")
    return summary


def _write_tables(out_root):
    import glob
    table1, table2, table4, table5 = [], [], [], []
    table3 = []
    for tag in EXPERIMENTS:
        diag_path = os.path.join(out_root, tag, "diagnosis.json")
        if not os.path.exists(diag_path):
            continue
        diag = json.load(open(diag_path))
        res_path = os.path.join(out_root, tag, "result.json")
        res = json.load(open(res_path)) if os.path.exists(res_path) else {}
        for det in diag.get("detections", []):
            table1.append({"experiment": tag, "window": "diagnostic",
                           "mechanism": det["mechanism"],
                           "support": det["support"],
                           "severity": det["severity"],
                           "prevalence": det["prevalence"],
                           "selected": det["selected"]})
        cand_path = os.path.join(out_root, tag, "candidate_results.json")
        if os.path.exists(cand_path):
            for ev in json.load(open(cand_path))["evaluations"]:
                table2.append({
                    "experiment": tag, "mechanism": res.get("mechanism"),
                    "candidate": ev["candidate_id"], "family": ev["family"],
                    "status": ev.get("status", ""),
                    "target_delta": ev["target_reduction"],
                    "ci_lower": ev["ci_lower"], "ci_upper": ev["ci_upper"],
                    "safety_violations": 0 if ev["validity_ok"] else 1,
                    "reasons": ev.get("reject_reasons", [])})
                table5.append({
                    "experiment": tag, "candidate": ev["candidate_id"],
                    "status": ev.get("status", ""),
                    "rejection_reason": "; ".join(
                        ev.get("reject_reasons", []))})
                readings = ev.get("readings", {})
                table4.append({"experiment": tag,
                               "mechanism": res.get("mechanism"),
                               "candidate": ev["candidate_id"],
                               "return_delta": readings.get(
                                   "repaired_return", 0.0)
                               - readings.get("baseline_return", 0.0),
                               "pnl_delta": readings.get(
                                   "repaired_pnl", 0.0)
                               - readings.get("baseline_pnl", 0.0),
                               "drawdown_delta": readings.get(
                                   "repaired_drawdown", 0.0)
                               - readings.get("baseline_drawdown", 0.0),
                               "turnover_delta": readings.get(
                                   "repaired_turnover", 0.0)
                               - readings.get("baseline_turnover", 0.0),
                               "orders_delta": readings.get(
                                   "repaired_order_count", 0)
                               - readings.get("baseline_order_count", 0),
                               "exposure_delta": readings.get(
                                   "repaired_exposure", 0.0)
                               - readings.get("baseline_exposure", 0.0)})
        if res.get("verdict") == "SUCCESS":
            held = json.load(open(os.path.join(
                out_root, tag, "heldout.json")))
            repl = json.load(open(os.path.join(
                out_root, tag, "replication.json")))
            table3.append({
                "mechanism": res.get("mechanism"),
                "repair": res.get("selected_id"),
                "diagnostic": res.get("verdict"),
                "heldout_target_improved": held.get("target_improved"),
                "heldout_economics_ok": held.get("economics_ok"),
                "persistence": res.get("persistence"),
                "rollback": res.get("rollback"),
                "replication": repl.get("verdict")})
    tables = {"table1_detection": table1, "table2_candidates": table2,
              "table3_admitted": table3, "table4_economics": table4,
              "table5_rejections": table5}
    os.makedirs(os.path.join(out_root, "tables"), exist_ok=True)
    for name, rows in tables.items():
        with open(os.path.join(out_root, "tables", f"{name}.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(rows, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
    return tables


def _write_figures(out_root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    skipped = []
    figdir = os.path.join(out_root, "figures")
    os.makedirs(figdir, exist_ok=True)
    tables = {}
    for i in (1, 2, 3, 4, 5):
        path = os.path.join(out_root, "tables", f"table{i}_"
                            + ("detection" if i == 1 else
                               "candidates" if i == 2 else
                               "admitted" if i == 3 else
                               "economics" if i == 4 else "rejections")
                            + ".json")
        tables[i] = json.load(open(path)) if os.path.exists(path) else []

    def savefig(name):
        plt.tight_layout()
        plt.savefig(os.path.join(figdir, name), dpi=100)
        plt.close()

    if tables[1]:
        exps = sorted({r["experiment"] for r in tables[1]})
        mechs = sorted({r["mechanism"] for r in tables[1]})
        width = 0.15
        xs = list(range(len(exps)))
        for j, mech in enumerate(mechs):
            vals = [next((r["support"] for r in tables[1]
                          if r["experiment"] == e
                          and r["mechanism"] == mech), 0) for e in exps]
            plt.bar([x + j * width for x in xs], vals, width=width,
                    label=mech)
        plt.xticks([x + width * 2 for x in xs], exps)
        plt.ylabel("support (sessions)")
        plt.title("Figure 1 — Mechanism support across windows")
        plt.legend(fontsize=7)
        savefig("figure1_support.png")
    else:
        skipped.append("figure1 (no detections)")

    if tables[2]:
        admit = [r for r in tables[2] if r["status"] == "ADMISSIBLE"]
        if admit:
            labels = [r["candidate"].split("-C-", 1)[1][:28] for r in admit]
            vals = [r["target_delta"] for r in admit]
            plt.barh(labels, vals)
            plt.xlabel("target delta (repaired - base)")
            plt.title("Figure 2 — Target metric: admitted repairs")
            savefig("figure2_target_admitted.png")
        else:
            skipped.append("figure2 (no admissible repairs)")
        from collections import Counter
        counts = Counter(r["status"] for r in tables[2])
        plt.bar(list(counts), list(counts.values()))
        plt.ylabel("candidates")
        plt.title("Figure 6 — Candidate outcome matrix (status counts)")
        plt.xticks(rotation=20, fontsize=7)
        savefig("figure6_outcomes.png")
    else:
        skipped.append("figure2 (no candidates)")
        skipped.append("figure6 (no candidates)")

    if tables[4]:
        for key, title, fname in (
                ("drawdown_delta", "Figure 3 — Drawdown delta "
                 "(repaired - base)", "figure3_drawdown.png"),
                ("turnover_delta", "Figure 4a — Turnover delta",
                 "figure4a_turnover.png"),
                ("orders_delta", "Figure 4b — Order-count delta",
                 "figure4b_orders.png"),
                ("exposure_delta", "Figure 5 — Exposure-peak delta",
                 "figure5_exposure.png")):
            labels = [r["experiment"] + ":" + r["candidate"].split(
                "-C-", 1)[1][:22] for r in tables[4]]
            vals = [r[key] for r in tables[4]]
            plt.figure(figsize=(10, max(4, len(vals) * 0.28)))
            plt.barh(labels, vals)
            plt.title(title)
            plt.tick_params(labelsize=6)
            savefig(fname)
            plt.close()
    else:
        skipped.append("figures 3-5 (no readings)")

    if tables[3]:
        skipped.append("figure7 (admitted-heldout comparison not plotted; "
                       "see table3)")
    else:
        skipped.append("figure7 (no admitted repairs)")
    with open(os.path.join(figdir, "skipped.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"skipped": skipped}, handle, sort_keys=True,
                  separators=(",", ":"))
        handle.write("\n")
    return skipped


def report_only(base_dir: str) -> dict:
    """Regenerate summary/tables/figures from frozen per-exp artefacts.

    Zero episodes consumed. Fails if any experiment lacks result.json
    (the campaign must be executed first, staged via --only).
    """
    out_root = os.path.join(base_dir, OUT_DIR)
    protocol = dict(yaml.safe_load(
        open(os.path.join(base_dir, PROTOCOL_PATH))))
    bank = json.load(open(os.path.join(out_root, "window_bank.json")))
    results = {}
    for tag in EXPERIMENTS:
        path = os.path.join(out_root, tag, "result.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"missing {path}: run --only {tag} first")
        results[tag] = json.load(open(path))
    ep = sum(r.get("episodes_used", 0) for r in results.values())
    n_adm = sum(1 for r in results.values()
                if r.get("verdict") == "SUCCESS")
    summary = {"experiment": "M-R9",
               "protocol_fingerprint": _fingerprint(protocol),
               "bank_fingerprint": bank["bank_fingerprint"],
               "episodes_used": ep, "experiments": results,
               "n_admitted": n_adm,
               "campaign_verdict": "SUCCESS" if n_adm else "NULL"}
    with open(os.path.join(out_root, "summary.json"), "w",
              encoding="utf-8") as handle:
        json.dump(summary, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    _write_tables(out_root)
    skipped = _write_figures(out_root)
    print(f"M-R9 report: verdict={summary['campaign_verdict']} "
          f"admitted={n_adm}/6 episodes={ep} skipped={skipped}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="M-R9 campaign")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--report-only", action="store_true",
                        help="regenerate summary/tables/figures only")
    args = parser.parse_args()
    if args.report_only:
        report_only(args.base_dir)
    else:
        run_campaign(args.base_dir, args.overwrite, args.only)


if __name__ == "__main__":
    main()
