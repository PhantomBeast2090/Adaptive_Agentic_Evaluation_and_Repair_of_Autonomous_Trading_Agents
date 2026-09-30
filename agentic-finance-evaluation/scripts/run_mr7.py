"""M-R7 mechanism-relative normality sensitivity experiment (additive).

Compares three frozen normality specifications (N0 regime-protected /
N1 mechanism-relative / N2 hybrid) over an IDENTICAL candidate set on
frozen M-R6 diagnostic evidence. Only admitted (spec, candidate) pairs
proceed to held-out; each pair is frozen independently first.

Isolation guarantees (asserted in code):
- candidates generated once; IDs/params identical across N0/N1/N2;
- heldout.json must not exist before a per-pair freeze record;
- normality functions receive (record, mechanism) only — enforced by
  signature inspection in tests, not just discipline.
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
from evaluation.repair.gate import paired_bootstrap_ci
from evaluation.repair.normality import (
    SPECIFICATIONS,
    annotate_exposure_active,
)
from evaluation.repair.schemas import FailureMechanism, MemoryEntry

PROTOCOL_PATH = "configs/adaptive_repair/mr7_normality.yaml"
OUT_DIR = "data/adaptive_repair/M-R7"
MR6_DIR = "data/adaptive_repair/M-R6"


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _mean(values):
    return sum(values) / len(values) if values else 0.0


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


def _inactivity(trace_records):
    n = len(trace_records)
    if not n:
        return 1.0
    quiet = sum(1 for r in trace_records if not r.get("submitted_orders"))
    return quiet / n


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
        "turnover": turnover,
        "inactivity_rate": inactivity / n if n else 1.0,
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


def run_mr7(base_dir: str, overwrite: bool = False) -> dict:
    from evaluation.diagnostics.repair.regression import analyze_regression
    from evaluation.diagnostics.repair.results import (
        RepairDecision, RepairResult, _decide)
    from evaluation.repair.adaptive import (
        CandidateEvaluation, adjudicate_candidates, generate_candidates)
    from evaluation.repair.gate import coverage_precheck

    protocol = dict(yaml.safe_load(
        open(os.path.join(base_dir, PROTOCOL_PATH))))
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
    mech_templates = protocol["mechanism_templates"]
    vix_map = natural.load_vix_map(base_dir)
    diag = protocol["windows"]["diagnostic"]

    def write(name: str, payload) -> str:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        return path

    for spec_id in ("N0", "N1", "N2"):
        entry = protocol["normality"].get(spec_id)
        if entry is None or spec_id not in SPECIFICATIONS:
            raise ValueError(f"unknown normality spec {spec_id!r}")
        actual = SPECIFICATIONS[spec_id].fingerprint()[:16]
        if actual != entry["fingerprint"]:
            raise ValueError(
                f"normality fingerprint mismatch for {spec_id}")
    protocol_fp = _fingerprint(protocol)
    write("protocol.yaml", protocol)
    chain.append("PROTOCOL_FROZEN", {
        "protocol_fingerprint": protocol_fp,
        "normality": {k: SPECIFICATIONS[k].fingerprint()[:16]
                      for k in ("N0", "N1", "N2")}})

    mr6_base_path = os.path.join(
        base_dir, "data", "adaptive_repair", "M-R6", "base_diagnostic.json")
    with open(mr6_base_path) as handle:
        base_records = json.load(handle)["records"]
    agent = _load_agent(protocol, base_dir)
    base_fp = fingerprint_agent(agent, agent.identity)
    with open(os.path.join(
            base_dir, "data", "adaptive_repair", "M-R6",
            "manifest.json")) as handle:
        mr6_manifest = json.load(handle)
    chain.append("BASE_REUSED", {
        "policy_fingerprint": base_fp,
        "n_records": len(base_records),
        "mr6_manifest": mr6_manifest.get("manifest_fingerprint", "")})
    sessions = natural.adapt_records(base_records, vix_map)

    detections = []
    for name in ("loss_chasing", "overtrading", "exposure", "volatility",
                 "drawdown"):
        from evaluation.repair.adaptive import DETECTORS
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
    with open(os.path.join(
            base_dir, "data", "adaptive_repair", "M-R6",
            "detections.json")) as handle:
        mr6_detections = json.load(handle)
    assert sorted(s.mechanism_id.replace(exp, "M-R6")
                  for s in detections) == sorted(
        d["mechanism_id"] for d in mr6_detections), \
        "detection must reproduce M-R6 exactly"
    detections.sort(key=lambda s: (-s.support, -s.severity,
                                   s.mechanism_id))
    mechanism = detections[0]
    assert mechanism.failure_type == "exposure"
    chain.append("MECHANISM_CONFIRMED", {
        "mechanism_id": mechanism.mechanism_id,
        "support": mechanism.support})

    template = mech_templates[mechanism.failure_type]
    max_names = int(protocol["detection"]["detector_params"]["exposure"][
        "max_normal_names"])
    annotated = annotate_exposure_active(sessions, max_names)
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
    with open(os.path.join(
            base_dir, "data", "adaptive_repair", "M-R6",
            "candidates.json")) as handle:
        mr6_candidates = json.load(handle)
    # Isolation: identical family/param sequences (IDs carry the
    # experiment prefix by design, so comparison strips it).
    def _suffix(candidate_id: str) -> str:
        return candidate_id.split("-C-", 1)[1]
    assert [_suffix(g.candidate_id) for g in generated] == [
        _suffix(c["candidate_id"])
        for c in mr6_candidates["generated"]], \
        "candidate set must match M-R6 exactly"
    assert [dict(g.params) for g in generated] == [
        dict(c["params"]) for c in mr6_candidates["generated"]], \
        "candidate params must match M-R6 exactly"
    chain.append("CANDIDATES_FROZEN", {"n": len(generated)})
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

    target_cfg = protocol["target"]
    block_size = int(target_cfg.get("block_size", 10))
    normal_qty = float(target_cfg.get("normal_quantity", 2.0))
    rep_traces = {}
    winner_entries = {}
    evaluations_base = {}
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
            _load_agent(protocol, base_dir), [entry], (entry.entry_id,),
            shadow=True)
        shadow_result = run_baseline(
            shadow, _build_config(protocol, f"{exp}-shadow-{gen.candidate_id}",
                                  diag, base_dir),
            base_dir=base_dir)
        shadow_records = [r.to_dict()
                          for r in shadow_result.decision_records]
        assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in shadow_records] == \
               [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in base_records], \
            f"shadow diverged for {gen.candidate_id}"
        served = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [entry], (entry.entry_id,))
        assert served.base_policy_fingerprint() == base_fp
        rep_result = run_baseline(
            served,
            _build_config(protocol, f"{exp}-rep-{gen.candidate_id}", diag, base_dir),
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
        base_orders = [json.dumps(r.get("submitted_orders", []),
                                  sort_keys=True) for r in base_records]
        rep_orders = [json.dumps(r.get("submitted_orders", []),
                                 sort_keys=True) for r in rep_records]
        fires = sum(1 for b, r in zip(base_orders, rep_orders) if b != r)
        evaluations_base[gen.candidate_id] = {
            "candidate_id": gen.candidate_id, "family": gen.family,
            "params": dict(gen.params),
            "spec_fingerprint": spec.fingerprint(),
            "target_reduction": sum(diffs) / len(diffs) if diffs else 0.0,
            "ci_lower": ci["lower"], "ci_upper": ci["upper"],
            "support": mechanism.support,
            "fires": fires,
            "suppression_rate": fires / len(base_records),
            "final_value": _trace_metrics(rep_records)["final_value"],
            "base_final_value": _trace_metrics(base_records)["final_value"],
            "drawdown": _trace_metrics(rep_records)["max_drawdown"],
            "base_drawdown": _trace_metrics(base_records)["max_drawdown"],
            "inactivity": _trace_metrics(rep_records)["inactivity_rate"],
            "base_inactivity": _trace_metrics(base_records)["inactivity_rate"],
            "policy_ok": True,
            "validity_ok": _trace_metrics(rep_records)["violations"] == 0,
        }
    write("candidate_results.json", {"evaluations": [
        evaluations_base[g.candidate_id] for g, _ in compiled]})
    chain.append("EVALUATED", {"n": len(compiled)})
    # ---- Normality matrix + conflict analysis (pre-adjudication) ----
    matrix = []
    for index, row in enumerate(annotated):
        protected = {k: SPECIFICATIONS[k].protected_session(
            row, mechanism.failure_type) for k in ("N0", "N1", "N2")}
        matrix.append({
            "session_id": row["session"],
            "mechanism_active": bool(row["exposure_active"]),
            "vix_regime": ("HIGH" if (row["vix"] or 0) > 25.0 else
                           ("LOW" if (row["vix"] or 0) < 15.0 else "MID")),
            "N0_protected": protected["N0"],
            "N1_protected": protected["N1"],
            "N2_protected": protected["N2"],
            "baseline_action": (
                "BUY" if row["buy_quantity"] > 0
                else ("SELL" if row["sell_quantity"] > 0 else "HOLD")),
        })
    write("normality_matrix.json", matrix)
    conflict = {}
    total = len(matrix)
    for spec_id in ("N0", "N1", "N2"):
        protected_rows = [r for r in matrix if r[f"{spec_id}_protected"]]
        conflict[spec_id] = {
            "protection_coverage": len(protected_rows) / total if total else 0.0,
            "mechanism_coverage": sum(
                1 for r in matrix if r["mechanism_active"]) / total if total else 0.0,
            "conflict_rate": sum(
                1 for r in protected_rows if r["mechanism_active"]
            ) / len(protected_rows) if protected_rows else 0.0,
        }
    write("conflict_analysis.json", conflict)
    chain.append("MATRIX", {"conflict": conflict})

    # ---- Adjudication per specification (independent) ----
    base_orders = [json.dumps(r.get("submitted_orders", []),
                              sort_keys=True) for r in base_records]
    rep_orders_by_id = {}
    for gen, spec in compiled:
        rep_records = rep_traces[gen.candidate_id]
        rep_orders_by_id[gen.candidate_id] = [
            json.dumps(r.get("submitted_orders", []),
                       sort_keys=True) for r in rep_records]
    adjudications = {}
    for spec_id in ("N0", "N1", "N2"):
        evaluations = []
        for gen, spec in compiled:
            rep_orders = rep_orders_by_id[gen.candidate_id]
            protected = [
                SPECIFICATIONS[spec_id].protected_session(row, "exposure")
                for row in annotated]
            normal_ok = all(
                b == r for b, r, keep
                in zip(base_orders, rep_orders, protected) if keep)
            record = dict(evaluations_base[gen.candidate_id])
            record["normal_preserved"] = bool(normal_ok)
            evaluations.append(CandidateEvaluation(**{
                k: record[k] for k in (
                    "candidate_id", "family", "params",
                    "spec_fingerprint", "target_reduction", "ci_lower",
                    "ci_upper", "support", "fires", "suppression_rate",
                    "normal_preserved", "final_value", "base_final_value",
                    "drawdown", "base_drawdown", "inactivity",
                    "base_inactivity", "policy_ok", "validity_ok")}))
        adjudication = adjudicate_candidates(
            evaluations,
            min_support=adj_cfg["min_support"],
            tolerance_value=adj_cfg["tolerance_value"],
            tolerance_drawdown=adj_cfg["tolerance_drawdown"])
        adjudications[spec_id] = {
            "ranked_ids": list(adjudication.ranked_ids),
            "selected_id": adjudication.selected_id,
            "reasons": {k: v for k, v in adjudication.reasons.items()},
            "rejected": list(adjudication.rejected)}
    write("adjudication.json", adjudications)
    with open(os.path.join(
            base_dir, "data", "adaptive_repair", "M-R6",
            "adjudication.json")) as handle:
        mr6_adjudication = json.load(handle)
    assert adjudications["N0"]["selected_id"].replace(
        exp, "M-R6", 1) == mr6_adjudication["selected_id"], \
        "N0 must reproduce the M-R6 adjudication result"
    assert sorted(r.replace(exp, "M-R6", 1)
                  for r in adjudications["N0"]["rejected"]) == sorted(
        mr6_adjudication["rejected"]), \
        "N0 rejection set must match M-R6"
    n0_reasons = {
        k.replace(exp, "M-R6", 1): v
        for k, v in adjudications["N0"]["reasons"].items()
        if k != "selection"}
    mr6_reasons = {
        k: v for k, v in mr6_adjudication["reasons"].items()
        if k != "selection"}
    assert n0_reasons == mr6_reasons, \
        "N0 rejection reasons must match M-R6"
    chain.append("ADJUDICATED", {
        spec_id: adjudications[spec_id]["selected_id"] or "NULL"
        for spec_id in ("N0", "N1", "N2")})
    # ---- Freeze + downstream per admitted (spec, candidate) pair ----
    held = protocol["windows"]["heldout"]
    rep_win = protocol["windows"]["replication"]
    results = {}
    for spec_id in ("N0", "N1", "N2"):
        selected_id = adjudications[spec_id]["selected_id"]
        tag = f"{exp}-{spec_id}"
        pair_dir = os.path.join(out_dir, spec_id)
        os.makedirs(pair_dir, exist_ok=True)

        def pair_write(name: str, payload, _dir=pair_dir) -> str:
            path = os.path.join(_dir, name)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True,
                          separators=(",", ":"))
                handle.write("\n")
            return path

        if not selected_id:
            pair_write("result.json", {
                "experiment": tag, "verdict": "NULL",
                "reason": "no admissible repair under " + spec_id})
            results[spec_id] = {"verdict": "NULL"}
            chain.append("PAIR_NULL", {"spec": spec_id})
            continue
        pair_write("freeze.json", {
            "selected_id": selected_id,
            "normality_id": spec_id,
            "normality_fingerprint": SPECIFICATIONS[spec_id].fingerprint(),
            "protocol_fingerprint": protocol_fp})
        chain.append("FROZEN", {"pair": tag, "selected": selected_id})
        assert not os.path.exists(os.path.join(pair_dir, "heldout.json")), \
            "held-out artefacts must not predate the freeze"
        selected = next(c for c, _ in compiled
                        if c.candidate_id == selected_id)
        from evaluation.repair.schemas import RepairSpec
        from evaluation.repair.schemas import MemoryEntry as EntryCls
        selected_spec = RepairSpec.from_dict(
            _spec_dict_for(compiled, selected_id))
        winner = EntryCls(
            entry_id=f"mem-{selected_id}-{spec_id}",
            agent_id=agent.identity.agent_id,
            spec=selected_spec,
            source_evaluation_id=f"{exp}-base-diag",
            diagnostic_evidence=(f"{exp}:natural:{spec_id}",),
            provenance={
                "mechanism_fingerprint": failure_mech.fingerprint(),
                "protocol_fingerprint": protocol_fp,
                "candidate_id": selected_id,
                "normality_id": spec_id,
                "normality_fingerprint": SPECIFICATIONS[
                    spec_id].fingerprint()})
        served_held = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [winner], (winner.entry_id,))
        base_held_result = run_baseline(
            _load_agent(protocol, base_dir),
            _build_config(protocol, f"{tag}-base-held", held, base_dir),
            base_dir=base_dir)
        rep_held_result = run_baseline(
            served_held,
            _build_config(protocol, f"{tag}-rep-held", held, base_dir),
            base_dir=base_dir)
        base_held_records = [r.to_dict()
                             for r in base_held_result.decision_records]
        rep_held_records = [r.to_dict()
                            for r in rep_held_result.decision_records]
        base_held_sessions = natural.adapt_records(
            base_held_records, vix_map)
        rep_held_sessions = natural.adapt_records(
            rep_held_records, vix_map)
        base_hvals = _block_values(base_held_sessions, 2.0, 10)
        rep_hvals = _block_values(rep_held_sessions, 2.0, 10)
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
            rep_held_metrics["final_value"]
            >= base_held_metrics["final_value"]
            * (1.0 - adj_cfg["tolerance_value"])
            and rep_held_metrics["max_drawdown"]
            <= base_held_metrics["max_drawdown"]
            + adj_cfg["tolerance_drawdown"])
        pair_write("heldout.json", {
            "base": base_held_metrics, "repaired": rep_held_metrics,
            "held_ci": held_ci, "target_improved": held_target_ok,
            "economics_ok": held_econ_ok})
        chain.append("HELDOUT", {"pair": tag,
                                 "target_improved": held_target_ok,
                                 "economics_ok": held_econ_ok})
        pair_result = {
            "experiment": tag, "selected_id": selected_id,
            "held_target_improved": held_target_ok,
            "held_economics_ok": held_econ_ok,
            "held_ci": held_ci,
            "policy_fingerprint": base_fp,
            "persistence": "NOT_ATTEMPTED",
            "rollback": "NOT_ATTEMPTED",
        }
        if not (held_target_ok and held_econ_ok):
            pair_write("result.json", dict(
                pair_result, verdict="NULL",
                reason="held-out gates failed: no admission"))
            results[spec_id] = {"verdict": "NULL"}
            chain.append("PAIR_NULL", {"spec": spec_id})
            continue
        winner_rep = rep_traces[selected_id]
        winner_entry = winner_entries[selected_id]
        comparisons = []
        for window, ref_records, val_records in (
                ("candidate_diagnostic", base_records, winner_rep),
                ("candidate_heldout", base_held_records, rep_held_records)):
            comparisons.extend([
                ("adaptive_target",
                 _block_mean(ref_records, 2.0, 10),
                 _block_mean(val_records, 2.0, 10)),
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
            baseline_evaluation_id=f"{exp}-base-diag",
            baseline_fingerprint=_fingerprint(base_records),
            diagnostic_state_fingerprint=failure_mech.fingerprint(),
            target_agent_identity=agent.identity,
            target_agent_fingerprint=base_fp,
            hypothesis_id=failure_mech.mechanism_id,
            hypothesis_fingerprint=failure_mech.fingerprint(),
            failure_class="exposure",
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
            analysis_id=f"{tag}-analysis",
            candidate_id=selected_id,
            validation_fingerprint=report.fingerprint(),
            comparisons=tuple(comparisons),
            tolerances=())
        decision, reason = _decide(
            report=report, analysis=analysis,
            target_metric=formal_metric,
            target_direction=ExpectedDirection.DECREASE)
        pair_write("validation_report.json", report.to_dict())
        pair_write("regression_analysis.json", analysis.to_dict())
        if decision != RepairDecision.ACCEPTED:
            pair_write("result.json", dict(
                pair_result, verdict="NULL",
                reason=f"formal gate refused: {reason}"))
            results[spec_id] = {"verdict": "NULL"}
            chain.append("PAIR_NULL", {"spec": spec_id})
            continue
        from evaluation.diagnostics.repair.results import RepairResult
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
            pair_write("result.json", dict(
                pair_result, verdict="NULL",
                reason=f"admission refused: {admission}"))
            results[spec_id] = {"verdict": "NULL"}
            chain.append("PAIR_NULL", {"spec": spec_id})
            continue
        store = store.admit(validated, admission)
        chain.append("ADMITTED", {"pair": tag,
                                  "store": store.fingerprint()})
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
                        "store_fingerprint": store.fingerprint(),
                        "normality_id": spec_id})
        from evaluation.repair import control_plane
        assert control_plane.verify_admission(store, serving)
        pair_write("memory_store.json", store.to_dict())
        pair_write("serving_entry.json", serving.to_dict())
        re_store = MemoryStore.from_dict(json.load(open(os.path.join(
            pair_dir, "memory_store.json"))))
        re_entry = MemoryEntry.from_dict(json.load(open(os.path.join(
            pair_dir, "serving_entry.json"))))
        assert re_store.fingerprint() == store.fingerprint()
        assert re_entry.fingerprint() == serving.fingerprint()
        re_served = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [re_entry],
            (re_entry.entry_id,))
        re_result = run_baseline(
            re_served, _build_config(protocol, f"{tag}-persist", diag, base_dir),
            base_dir=base_dir)
        re_records = [r.to_dict() for r in re_result.decision_records]
        assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in re_records] == \
               [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in winner_rep]
        assert re_served.base_policy_fingerprint() == base_fp
        chain.append("PERSISTED", {"pair": tag})
        pair_result = dict(
            pair_result, persistence="REPRODUCED", rollback="PENDING")
        rolled = MemoryConditionedAgent(
            _load_agent(protocol, base_dir), [re_entry], ())
        roll_result = run_baseline(
            rolled, _build_config(protocol, f"{tag}-rollback", diag, base_dir),
            base_dir=base_dir)
        roll_records = [r.to_dict() for r in roll_result.decision_records]
        assert [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in roll_records] == \
               [json.dumps(r.get("submitted_orders", []), sort_keys=True)
                for r in base_records]
        assert rolled.base_policy_fingerprint() == base_fp
        chain.append("ROLLED_BACK", {"pair": tag})
        pair_write("result.json", dict(
            pair_result, verdict="SUCCESS", persistence="REPRODUCED",
            rollback="RESTORED",
            store_fingerprint=store.fingerprint()))
        results[spec_id] = {"verdict": "SUCCESS"}
        # Replication (acceptance-gated, pre-registered window).
        rep_base_result = run_baseline(
            _load_agent(protocol, base_dir),
            _build_config(protocol, f"{tag}-repl-base", rep_win, base_dir),
            base_dir=base_dir)
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
            rep_rep_result = run_baseline(
                rep_served,
                _build_config(protocol, f"{tag}-repl-rep", rep_win, base_dir),
                base_dir=base_dir)
            rep_rep_records = [r.to_dict()
                               for r in rep_rep_result.decision_records]
            rep_rep_sessions = natural.adapt_records(rep_rep_records,
                                                     vix_map)
            base_vals = _block_values(rep_base_sessions, 2.0, 10)
            rep_vals = _block_values(rep_rep_sessions, 2.0, 10)
            diffs = [r["value"] - b["value"]
                     for r, b in zip(rep_vals, base_vals)]
            replication["mean_diff"] = sum(diffs) / len(diffs) if diffs else 0.0
            replication["verdict"] = ("REPLICATED"
                                      if diffs and replication["mean_diff"] < 0
                                      else "NOT-REPLICATED")
            assert rep_served.base_policy_fingerprint() == base_fp
        pair_write("replication.json", replication)
        chain.append("REPLICATED",
                     {"pair": tag, "verdict": replication["verdict"]})
        results[spec_id]["replication"] = replication["verdict"]
    if not any(v.get("verdict") == "SUCCESS"
               for v in results.values()):
        overall = "NULL"
    else:
        overall = "SUCCESS"
    return _finish(out_dir, write, chain, protocol, protocol_fp,
                   base_fp, verdict=overall,
                   reason="M-R7 sensitivity complete",
                   extra={"per_spec": results})


def _spec_dict_for(compiled, selected_id):
    for gen, spec in compiled:
        if gen.candidate_id == selected_id:
            return spec.to_dict()
    raise KeyError(f"unknown candidate {selected_id}")


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
    parser = argparse.ArgumentParser(description="M-R7 normality experiment")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run_mr7(args.base_dir, args.overwrite)


if __name__ == "__main__":
    main()
