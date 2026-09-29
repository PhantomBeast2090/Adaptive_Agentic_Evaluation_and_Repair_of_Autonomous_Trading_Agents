"""Controlled repair execution (M-R2/M-R3).

CONTROLLED-KNOWN-MECHANISM benchmarks: engineering/causal validation of
the MemoryStore -> MemoryConditionedAgent repair path. NOT natural-market
discovery; makes no Indian-market mining claim.

Pipeline per benchmark (protocol YAML pre-registered, outcome-blind):
  BASE (run_baseline, sealed) -> flaw confirmation -> compile ->
  MemoryEntry (staging) -> SHADOW (behaviour equality) ->
  ACTIVE via run_validation(candidate=MemoryConditionedAgent, 3 runs) ->
  custom metrics + analyze_regression + _decide + block bootstrap +
  coverage -> ACCEPT/REJECT/NSF -> admission (extract/adjudicate/admit)
  -> persistence round-trip -> rollback -> manifest.

Frozen reuse: run_baseline, run_validation, analyze_regression, _decide,
DeterministicRuleProvider, extract_candidate, adjudicate,
MemoryStore.admit, GuardrailedAgent enforcement semantics, E1 metrics.
"""

from __future__ import annotations

import argparse
import csv
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
from evaluation.context.gate import adjudicate
from evaluation.context.extraction import extract_candidate
from evaluation.context.memory import MemoryStore
from evaluation.contracts.budget import EvaluationBudget
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.provider import DeterministicRuleProvider
from evaluation.diagnostics.repair.regression import (
    ToleranceRule,
    analyze_regression,
)
from evaluation.diagnostics.repair.results import RepairDecision, RepairResult
from evaluation.diagnostics.repair.validation import run_validation
from evaluation.diagnostics.repair.results import _decide
from evaluation.repair import control_plane
from evaluation.repair.audit import AuditChain
from evaluation.repair.compiler import compile as compile_mech
from evaluation.repair.gate import (
    assemble_verification,
    block_bootstrap_ci,
    coverage_precheck,
)
from evaluation.repair.schemas import FailureMechanism, MemoryEntry

PROTOCOL_DIR = "configs/controlled_repair"
OUT_ROOT = "data/controlled_repair"
VIX_PATH = "data/processed/india/market/nse_india_vix_daily.csv"


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_protocol(base_dir: str, name: str) -> dict:
    with open(os.path.join(base_dir, PROTOCOL_DIR, f"{name}_protocol.yaml")) as h:
        return yaml.safe_load(h)


def protocol_fingerprint(base_dir: str, name: str) -> str:
    with open(os.path.join(base_dir, PROTOCOL_DIR, f"{name}_protocol.yaml"),
              "rb") as h:
        return hashlib.sha256(h.read()).hexdigest()


def load_vix(base_dir: str) -> dict:
    out = {}
    with open(os.path.join(base_dir, VIX_PATH)) as h:
        for row in csv.DictReader(h):
            out[row["date"]] = float(row["close"])
    return out


def build_agent(protocol: dict):
    module_name, _, class_name = protocol["agent"]["module"].rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()


def build_config(experiment_id: str, window: dict, env: dict) -> BaselineConfig:
    return BaselineConfig(
        evaluation_id=experiment_id,
        start_date=window["start"],
        end_date=window["end"],
        universe={
            "nse_equity": env["universe"]["nse_equity"],
            "mcx_gold": ["GOLDAUG2023"],
        },
        transaction_cost_bps=float(env.get("transaction_cost_bps", 5.0)),
        initial_cash=float(env.get("initial_cash", 100000.0)),
        strict_pit=bool(env.get("strict_pit", True)),
        vintage_policy=str(env.get("vintage_policy", "explicit")),
        budget=EvaluationBudget(
            max_episodes=10, max_tests=None, max_repairs=None,
            max_validation_runs=None, max_runtime=None),
        seed=None,
    )


def records_payload(result) -> dict:
    return {
        "records": [r.to_dict() for r in result.decision_records],
        "metrics": [m.to_dict() for m in result.metrics],
    }


def metric_value(result, name: str):
    for metric in result.metrics:
        if metric.name == name:
            return metric.value
    return None


def custom_metrics(records, vix: dict, threshold: float, cap=None) -> dict:
    """Benchmark target metrics from decision records + VIX map."""
    high_buys = 0
    post_loss_qtys = []
    prev_reward = None
    escalations = 0
    for record in records:
        ts = record.get("decision_timestamp", "")
        session_vix = vix.get(ts)
        reward = record.get("reward", 0.0) or 0.0
        for side, qty, _ in [
            (o.get("side"), float(o.get("quantity", 0.0)), None)
            for o in record.get("submitted_orders", [])
        ]:
            if side == "BUY" and session_vix is not None \
                    and session_vix > threshold:
                high_buys += 1
            if side == "BUY" and prev_reward is not None \
                    and prev_reward < 0:
                post_loss_qtys.append(qty)
                if cap is not None and qty > cap:
                    escalations += 1
        prev_reward = reward
    return {
        "high_vix_buy_count": float(high_buys),
        "max_post_loss_quantity": float(max(post_loss_qtys))
        if post_loss_qtys else 0.0,
        "escalation_events": float(escalations),
    }


def run_benchmark(base_dir: str, name: str, overwrite: bool = False) -> dict:
    protocol = load_protocol(base_dir, name)
    exp = protocol["experiment"]
    out_dir = os.path.join(base_dir, OUT_ROOT, exp)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    vix = load_vix(base_dir)
    threshold = float(protocol["vix_threshold"]) if "vix_threshold" in protocol else 25.0
    chain = AuditChain()

    def write(fname: str, payload) -> str:
        path = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")
        return path

    # ---- Phase 1: BASE (sealed diagnostic run) ----
    agent = build_agent(protocol)
    base_fp = fingerprint_agent(agent, agent.identity)
    diag = protocol["windows"]["diagnostic"]
    base_result = run_baseline(
        agent, build_config(f"{exp}-base-diag", diag, protocol["environment"]),
        base_dir=base_dir)
    base_records = [r.to_dict() for r in base_result.decision_records]
    write("base_diagnostic.json", records_payload(base_result))
    chain.append("BASE_SEALED", {
        "policy_fingerprint": base_fp,
        "result_fingerprint": base_result.fingerprint(),
        "n_records": len(base_records)})

    # ---- Phase 2: controlled diagnosis (pre-registered mechanism + check)
    mech_cfg = protocol["mechanism"]
    # The quantity cap is pre-registered in the protocol repair block and
    # carried into the compiler via scope_hint (the compiler never invents
    # caps; missing cap -> UNCOMPILABLE).
    scope_hint = dict(mech_cfg.get("scope_hint", {}))
    protocol_cap = (protocol.get("repair", {}).get("rule_params", {}) or {}
                    ).get("cap")
    if protocol_cap is not None and "max_quantity_cap" not in scope_hint:
        scope_hint["max_quantity_cap"] = protocol_cap
    mechanism = FailureMechanism(
        mechanism_id=mech_cfg["id"],
        taxonomy=mech_cfg["taxonomy"],
        condition=(f"protocol:{mech_cfg['id']}",),
        scope_hint=scope_hint,
        trigger_hint=tuple(tuple(t) for t in mech_cfg.get("trigger_hint", [])),
        evidence_refs=(base_result.fingerprint(),),
        provenance={"protocol": name, "experiment": exp,
                    "label": protocol["label"]},
    )
    cap = (protocol.get("repair", {}).get("rule_params", {}) or {}).get("cap")
    base_custom = custom_metrics(base_records, vix, threshold, cap)
    if name == "mr2":
        assert base_custom["high_vix_buy_count"] > 0, \
            "flaw absent: no high-VIX BUYs in diagnostic"
    else:
        assert base_custom["escalation_events"] > 0, \
            "flaw absent: no quantity escalation in diagnostic"
    chain.append("DIAGNOSED", {"mechanism": mechanism.fingerprint(),
                               "base_custom": base_custom})

    # ---- Compile -> staging MemoryEntry ----
    compiled = compile_mech(mechanism, f"spec-{exp}")
    from evaluation.repair.compiler import Uncompilable
    assert not isinstance(compiled, Uncompilable), \
        f"controlled mechanism uncompilable: {compiled}"
    assert compiled.rule_type == protocol["repair"]["rule_type"]
    entry = MemoryEntry(
        entry_id=f"mem-{exp}",
        agent_id=agent.identity.agent_id,
        spec=compiled,
        source_evaluation_id=f"{exp}-base-diag",
        diagnostic_evidence=(f"{exp}:controlled-flaw",),
        provenance={"mechanism_fingerprint": mechanism.fingerprint(),
                    "protocol_fingerprint": protocol_fingerprint(base_dir, name)},
    )
    chain.append("COMPILED", {"spec": compiled.fingerprint(),
                              "entry": entry.fingerprint()})

    # ---- Phase 3a: SHADOW (behaviour equality, prediction recorded)
    shadow = MemoryConditionedAgent(build_agent(protocol), [entry],
                                    (entry.entry_id,), shadow=True)
    shadow_result = run_baseline(
        shadow, build_config(f"{exp}-shadow-diag", diag,
                             protocol["environment"]),
        base_dir=base_dir)
    shadow_records = [r.to_dict() for r in shadow_result.decision_records]
    assert shadow_records == base_records, \
        "shadow run must reproduce base behaviour exactly"
    assert shadow.shadow_log(), "shadow must record predictions"
    n_predicted = sum(
        1 for s in shadow.shadow_log()
        if s["predicted_fingerprint"] != s["base_orders_fingerprint"])
    chain.append("SHADOWED", {"predicted_interventions": n_predicted})

    # ---- Phase 3b: ACTIVE via frozen run_validation (serving path) ----
    served = MemoryConditionedAgent(build_agent(protocol), [entry],
                                    (entry.entry_id,))
    assert served.base_policy_fingerprint() == base_fp
    held = protocol["windows"]["heldout"]
    report, artefacts = run_validation(
        validation_id=f"{exp}-validation",
        candidate_id=f"{exp}-candidate",
        candidate_fingerprint=_fingerprint({
            "wrapper": served.identity.agent_id,
            "spec": compiled.fingerprint()}),
        candidate_agent=served,
        original_agent=build_agent(protocol),
        baseline=base_result,
        heldout_window=(held["start"], held["end"]),
        seed=protocol["statistics"]["seed"],
        base_dir=base_dir)
    runs = {run.label: run for run in report.runs}
    # Artefacts share one validation evaluation_id; align by run order.
    art = {run.label: result for run, result in zip(report.runs, artefacts)}
    cand_diag_id = "candidate_diagnostic"
    chain.append("VALIDATED", {"report": report.fingerprint()})

    # ---- Metrics, regression, decision ----
    target = protocol["targets"]["primary"]["metric"]
    cand_diag_recs = [r.to_dict()
                      for r in art["candidate_diagnostic"].decision_records]
    cand_held_recs = [r.to_dict()
                      for r in art["candidate_heldout"].decision_records]
    orig_held_recs = [r.to_dict()
                      for r in art["original_heldout"].decision_records]
    cand_diag_custom = custom_metrics(cand_diag_recs, vix, threshold, cap)
    cand_held_custom = custom_metrics(cand_held_recs, vix, threshold, cap)
    orig_held_custom = custom_metrics(orig_held_recs, vix, threshold, cap)

    def custom_or_metric(records, result, metric_name):
        if metric_name in ("high_vix_buy_count", "max_post_loss_quantity",
                           "escalation_events"):
            return {"base_diag": custom_metrics(
                [r.to_dict() for r in base_result.decision_records],
                vix, threshold, cap)[metric_name],
                "cand_diag": cand_diag_custom[metric_name],
                "orig_held": orig_held_custom[metric_name],
                "cand_held": cand_held_custom[metric_name]}[records]
        return metric_value(result, metric_name)

    comparisons = []
    metric_names = ([target]
                    + list(protocol["targets"].get("regression", []))
                    + ["turnover", "inactivity_rate", "invalid_order_count",
                       "universe_violation_count", "no_price_count",
                       "calendar_gate_count"])
    seen = set()
    for metric_name in metric_names:
        if metric_name in seen:
            continue
        seen.add(metric_name)
        comparisons.append((
            "candidate_diagnostic", metric_name,
            custom_or_metric("base_diag", base_result, metric_name),
            custom_or_metric("cand_diag",
                             art["candidate_diagnostic"], metric_name)))
        comparisons.append((
            "candidate_heldout", metric_name,
            custom_or_metric("orig_held",
                             art["original_heldout"], metric_name),
            custom_or_metric("cand_held",
                             art["candidate_heldout"], metric_name)))
    tolerances = tuple(
        ToleranceRule(metric_name=t["metric_name"], epsilon=t["epsilon"])
        for t in protocol["targets"].get("tolerances", []))
    analysis = analyze_regression(
        analysis_id=f"{exp}-analysis",
        candidate_id=f"{exp}-candidate",
        validation_fingerprint=report.fingerprint(),
        comparisons=tuple(comparisons),
        tolerances=tolerances)
    decision, reason = _decide(
        report=report, analysis=analysis, target_metric=target,
        target_direction=ExpectedDirection.DECREASE)
    chain.append("DECIDED", {"decision": str(decision), "reason": reason})

    # ---- Statistics: paired block bootstrap + coverage ----
    stats_cfg = protocol["statistics"]
    by_ts = {r.get("decision_timestamp"): r for r in base_records}
    diag_diffs, held_diffs = [], []
    for record in cand_diag_recs:
        mate = by_ts.get(record.get("decision_timestamp"))
        if mate is not None:
            diag_diffs.append((record.get("reward", 0.0) or 0.0)
                              - (mate.get("reward", 0.0) or 0.0))
    held_base = {r.get("decision_timestamp"): r for r in orig_held_recs}
    for record in cand_held_recs:
        mate = held_base.get(record.get("decision_timestamp"))
        if mate is not None:
            held_diffs.append((record.get("reward", 0.0) or 0.0)
                              - (mate.get("reward", 0.0) or 0.0))
    from evaluation.repair.gate import block_bootstrap_ci
    diag_ci = block_bootstrap_ci(
        diag_diffs, seed=stats_cfg["seed"], block_len=stats_cfg["block_len"],
        n_boot=stats_cfg["n_boot"], alpha=stats_cfg["alpha"])
    held_ci = block_bootstrap_ci(
        held_diffs, seed=stats_cfg["seed"] + 1,
        block_len=stats_cfg["block_len"], n_boot=stats_cfg["n_boot"],
        alpha=stats_cfg["alpha"])
    fires = sum(
        1 for c, b in zip(cand_diag_recs, base_records)
        if [ (o.get("side"), o.get("quantity")) for o in c.get("submitted_orders", [])]
        != [ (o.get("side"), o.get("quantity")) for o in b.get("submitted_orders", [])])
    cov_cfg = protocol.get("coverage", {})
    min_fires = int(cov_cfg.get("min_fires",
                                cov_cfg.get("min_escalations", 1)))
    coverage = {"fires": fires, "min_fires": min_fires,
                "passed": fires >= min_fires}
    required = set(stats_cfg.get("require_lower_above_zero", []))
    ci_ok = True
    if "diagnostic" in required and not diag_ci["lower"] > 0:
        ci_ok = False
    if "heldout" in required and not held_ci["lower"] > 0:
        ci_ok = False
    chain.append("GATED", {"diag_ci": diag_ci, "held_ci": held_ci,
                           "coverage": coverage, "ci_ok": ci_ok})

    # ---- Verdict (no forcing) ----
    if decision == RepairDecision.ACCEPTED and ci_ok and coverage["passed"]:
        verdict = "ACCEPT"
    elif decision == RepairDecision.REJECTED:
        verdict = "REJECT"
    else:
        verdict = "NSF"
    verification = assemble_verification(
        verification_id=f"{exp}-verification",
        candidate_fingerprint=_fingerprint({"wrapper": served.identity.agent_id}),
        validation_fingerprint=report.fingerprint(),
        regression_fingerprint=analysis.fingerprint(),
        metric_deltas={target: {"diagnostic": [
            a for a in comparisons
            if a[0] == "candidate_diagnostic" and a[1] == target][0][2:],
            "heldout": [
            a for a in comparisons
            if a[0] == "candidate_heldout" and a[1] == target][0][2:]}},
        bootstrap_ci={"diagnostic": diag_ci, "heldout": held_ci},
        provenance={"protocol_fingerprint": protocol_fingerprint(base_dir, name),
                    "decision": str(decision), "reason": reason,
                    "coverage": coverage})
    # assemble_verification defaults NSF; ACCEPT only on full pass:
    from evaluation.repair.schemas import RepairVerification
    verification = RepairVerification(
        verification_id=verification.verification_id,
        candidate_fingerprint=verification.candidate_fingerprint,
        validation_fingerprint=verification.validation_fingerprint,
        regression_fingerprint=verification.regression_fingerprint,
        decision_fingerprint=verification.decision_fingerprint,
        metric_deltas=dict(verification.metric_deltas),
        bootstrap_ci=dict(verification.bootstrap_ci),
        persistence_fingerprint="",
        verdict=verdict,
        provenance=dict(verification.provenance))
    write("verification.json", verification.to_dict())
    write("analysis.json", analysis.to_dict())
    write("validation_report.json", report.to_dict())
    chain.append("VERDICT", {"verdict": verdict})

    result_payload = {
        "experiment": exp, "verdict": verdict,
        "target": target,
        "base_custom": base_custom,
        "candidate_diagnostic_custom": cand_diag_custom,
        "candidate_heldout_custom": cand_held_custom,
        "original_heldout_custom": orig_held_custom,
        "diag_ci": diag_ci, "held_ci": held_ci, "coverage": coverage,
        "decision": str(decision), "reason": reason,
        "policy_fingerprint": base_fp,
    }

    if verdict == "ACCEPT":
        # ---- Admission through the frozen path ----
        provider = DeterministicRuleProvider()
        proposal = provider.propose(
            repair_id=f"{exp}-repair",
            diagnostic_id=f"{exp}-diagnosis",
            baseline_evaluation_id=f"{exp}-base-diag",
            baseline_fingerprint=base_result.fingerprint(),
            diagnostic_state_fingerprint=mechanism.fingerprint(),
            target_agent_identity=agent.identity,
            target_agent_fingerprint=base_fp,
            hypothesis_id=mechanism.mechanism_id,
            hypothesis_fingerprint=mechanism.fingerprint(),
            failure_class=mech_cfg["taxonomy"],
            evidence_refs=(base_result.fingerprint(),
                           mechanism.fingerprint()),
        )
        result = RepairResult(
            repair_id=f"{exp}-repair",
            proposal_fingerprint=proposal.fingerprint(),
            candidate_id=f"{exp}-candidate",
            candidate_fingerprint=_fingerprint(
                {"wrapper": served.identity.agent_id}),
            validation_fingerprint=report.fingerprint(),
            analysis_fingerprint=analysis.fingerprint(),
            decision=RepairDecision.ACCEPTED,
            reason=reason,
            suggested_stopping=None,
            method="control-plane",
            method_version="v1")
        candidate_ctx = extract_candidate(
            proposal=proposal, result=result, report=report,
            analysis=analysis)
        store = MemoryStore(store_id=f"{exp}-store", entries=())
        validated, admission = adjudicate(
            candidate=candidate_ctx, result=result, report=report,
            analysis=analysis, store=store, proposal=proposal)
        from evaluation.context.gate import AdmissionDecision
        assert admission.decision is AdmissionDecision.ADMITTED, \
            f"admission refused: {admission}"
        store = store.admit(validated, admission)
        chain.append("ADMITTED", {
            "context": validated.fingerprint(),
            "store": store.fingerprint()})
        # Serving entry linked to the admitted context:
        serving = MemoryEntry(
            entry_id=entry.entry_id, agent_id=entry.agent_id,
            spec=entry.spec, source_evaluation_id=entry.source_evaluation_id,
            diagnostic_evidence=entry.diagnostic_evidence,
            priority=entry.priority, sequence=entry.sequence,
            provenance={**dict(entry.provenance),
                        "admission_verdict_fingerprint": admission.fingerprint()
                        if hasattr(admission, "fingerprint") else "",
                        "candidate_fingerprint": validated.fingerprint(),
                        "store_fingerprint": store.fingerprint()},
        )
        assert control_plane.verify_admission(store, serving)
        write("memory_store.json", store.to_dict())
        write("serving_entry.json", serving.to_dict())
        result_payload["store_fingerprint"] = store.fingerprint()
        result_payload["admitted_context"] = validated.fingerprint()

        # ---- Persistence round-trip ----
        re_store = MemoryStore.from_dict(
            json.load(open(os.path.join(out_dir, "memory_store.json"))))
        assert re_store.fingerprint() == store.fingerprint()
        re_entry = MemoryEntry.from_dict(
            json.load(open(os.path.join(out_dir, "serving_entry.json"))))
        assert re_entry.fingerprint() == serving.fingerprint()
        re_served = MemoryConditionedAgent(
            build_agent(protocol), [re_entry], (re_entry.entry_id,))
        re_result = run_baseline(
            re_served, build_config(f"{exp}-persist-diag", diag,
                                    protocol["environment"]),
            base_dir=base_dir)
        re_records = [r.to_dict() for r in re_result.decision_records]
        assert re_records == cand_diag_recs, \
            "reloaded repair must reproduce conditioned behaviour exactly"
        assert re_served.base_policy_fingerprint() == base_fp
        chain.append("PERSISTED", {
            "store": re_store.fingerprint(),
            "behaviour_reproduced": True})
        result_payload["persistence"] = "REPRODUCED"

        # ---- Rollback ----
        rolled = MemoryConditionedAgent(
            build_agent(protocol), [re_entry], ())
        roll_result = run_baseline(
            rolled, build_config(f"{exp}-rollback-diag", diag,
                                 protocol["environment"]),
            base_dir=base_dir)
        roll_records = [r.to_dict() for r in roll_result.decision_records]
        assert roll_records == base_records, \
            "deactivation must restore base behaviour exactly"
        assert rolled.base_policy_fingerprint() == base_fp
        chain.append("ROLLED_BACK", {"restored": True})
        result_payload["rollback"] = "RESTORED"
    else:
        result_payload["persistence"] = "NOT_ATTEMPTED"
        result_payload["rollback"] = "NOT_ATTEMPTED"

    write("result.json", result_payload)
    from evaluation.repair.audit import write_audit_log
    audit_records = chain.to_list()
    write("audit.json", audit_records)
    manifest = {
        "experiment": exp,
        "label": protocol["label"],
        "protocol_fingerprint": protocol_fingerprint(base_dir, name),
        "verdict": verdict,
        "policy_fingerprint": base_fp,
        "fingerprints": {
            "mechanism": mechanism.fingerprint(),
            "spec": compiled.fingerprint(),
            "entry": entry.fingerprint(),
            "base_result": base_result.fingerprint(),
            "validation": report.fingerprint(),
            "analysis": analysis.fingerprint(),
        },
    }
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    print(f"{exp}: verdict={verdict} decision={decision}")
    return result_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled repair benchmarks")
    parser.add_argument("--benchmark", choices=["mr2", "mr3"], required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run_benchmark(args.base_dir, args.benchmark, args.overwrite)


if __name__ == "__main__":
    main()
