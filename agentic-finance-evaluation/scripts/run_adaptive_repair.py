"""Adaptive repair experiment orchestrator (M-R5).

Runs one frozen protocol end-to-end with no human in the loop:
  load+freeze protocol -> build diagnostic feed -> BASELINE run ->
  detect mechanism -> generate candidates (diagnostic ONLY) ->
  compile all -> shadow all -> verify all on diagnostic ->
  adjudicate -> freeze winner -> held-out (winner only) ->
  admission decision -> persistence + rollback (if admitted) ->
  artefacts + report.

Held-out data is constructed lazily inside run_heldout(), which is
only invoked after freeze.json exists on disk. The generator and
adjudicator signatures structurally cannot receive held-out data
(anti-leakage by construction; pinned by tests).
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
from benchmarks import adaptive_feeds as feeds
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
from evaluation.repair.adaptive import (
    DETECTORS,
    adjudicate_candidates,
    eligible_families,
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


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _load_agent(path: str):
    module_name, _, class_name = path.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _build_feed(feed_cfg, names, starts):
    if "prices" in feed_cfg:
        base = [round(float(x), 4) for x in feed_cfg["prices"]]
        return {name: base * feed_cfg.get("n_blocks", 1) for name in names}
    unit = feed_cfg["unit"]
    n_blocks = feed_cfg["n_blocks"]
    out = {}
    for name, start in zip(names, starts):
        prices, price = [], float(start)
        for _ in range(n_blocks):
            for ret in unit:
                price *= 1.0 + float(ret)
                prices.append(round(price, 4))
        out[name] = prices
    return out


def _build_vix(feed_cfg):
    if "vix" in feed_cfg:
        base = list(feed_cfg["vix"])
        return base * feed_cfg.get("n_blocks", 1)
    return None


def _episode_values(trace, episodes, target_cfg, vix_series=None):
    field = target_cfg["field"]
    aggregate = target_cfg.get("aggregate", "sum")
    normal_qty = target_cfg.get("normal_quantity")
    sessions = {s["session"]: s for s in trace["sessions"]}
    out = []
    for index, (start, end) in enumerate(episodes):
        values = []
        for session in range(start, end + 1):
            row = sessions[session]
            if target_cfg.get("episode_filter") == "high_vix_only":
                vix = (vix_series[session] if vix_series is not None
                       and session < len(vix_series) else None)
                if vix is None or vix <= 25.0:
                    continue
            value = float(row.get(field, 0.0) or 0.0)
            if aggregate == "excess_sum" and normal_qty is not None:
                value = max(0.0, value - normal_qty)
            values.append(value)
        if aggregate == "max":
            out.append({"start": start, "end": end,
                        "value": max(values) if values else 0.0})
        else:
            out.append({"start": start, "end": end, "value": sum(values)})
    return out


def _compliant_mask(trace, normal_bound, vix_series=None):
    """Base-behaviour compliance per session (no episode logic).

    A session is compliant iff the BASE action was already within normal
    bounds. Protection rule (frozen): a protected session must be
    bit-identical under repair, where protected means compliant AND
    outside the candidate's declared scope (trigger inactive and, for
    cooldown specs, outside armed suppression windows).
    """
    kind = normal_bound["kind"]
    mask = []
    for row in trace["sessions"]:
        session = row["session"]
        if kind == "quantity":
            mask.append(float(row.get("buy_quantity", 0.0) or 0.0)
                        <= normal_bound["normal_quantity"] + 1e-9)
        elif kind == "orders":
            mask.append(int(row.get("order_count", 0) or 0)
                        <= normal_bound["max_normal_orders"])
        elif kind == "names":
            mask.append(int(row.get("names_held", 0) or 0)
                        <= normal_bound["max_normal_names"])
        elif kind == "vix_calm":
            vix = (vix_series[session] if vix_series is not None
                   and session < len(vix_series) else None)
            mask.append(vix is not None and vix <= normal_bound["vix_high"])
        else:
            raise ValueError(f"unknown normal_bound kind {kind!r}")
    return mask


def _trigger_matches(trigger, row, vix_series):
    """Evaluate trigger clauses against a base-trace session row."""
    for field_name, op, expected in trigger:
        if field_name == "vix":
            value = (vix_series[row["session"]]
                     if vix_series is not None
                     and row["session"] < len(vix_series) else None)
        elif field_name == "drawdown":
            equity = row.get("value", 0.0) or 0.0
            unrealized = row.get("unrealized", 0.0) or 0.0
            value = (max(0.0, -unrealized / equity)
                     if equity > 0 else None)
        elif field_name == "buy_present":
            value = row.get("buy_quantity", 0.0) > 0
        elif field_name == "sell_present":
            value = False
        elif field_name == "cash":
            value = row.get("cash")
        elif field_name == "exposure":
            value = 0.0
        elif field_name == "date":
            value = f"S{row['session']:04d}"
        else:
            raise ValueError(f"unsupported trigger field {field_name!r}")
        if value is None:
            return False
        if op == "eq":
            ok = value == expected
        elif op == "ne":
            ok = value != expected
        elif op == "gt":
            ok = value > expected
        elif op == "gte":
            ok = value >= expected
        elif op == "lt":
            ok = value < expected
        elif op == "lte":
            ok = value <= expected
        elif op == "in":
            ok = value in expected
        elif op == "not_in":
            ok = value not in expected
        else:
            raise ValueError(f"unknown trigger operator {op!r}")
        if not ok:
            return False
    return True


def _armed_windows(base_sessions, trigger, horizon, vix_series=None):
    """Cooldown suppression windows simulated on the base trace."""
    armed = set()
    last_arm = -10 ** 9
    for row in base_sessions:
        session = row["session"]
        if _trigger_matches(trigger, row, vix_series):
            last_arm = session
        if session <= last_arm + horizon:
            armed.add(session)
    return armed


def _protected_mask(base_trace, spec_trigger, rule_type, rule_params,
                    normal_bound, vix_series):
    """Protected sessions: compliant AND outside declared repair scope."""
    compliant = _compliant_mask(base_trace, normal_bound, vix_series)
    horizon = (rule_params.get("sessions", 0)
               if rule_type == "cooldown_after_loss" else 0)
    armed = (_armed_windows(base_trace["sessions"], spec_trigger, horizon,
                            vix_series)
             if rule_type == "cooldown_after_loss" else set())
    protected = []
    for row, is_compliant in zip(base_trace["sessions"], compliant):
        in_scope = _trigger_matches(spec_trigger, row, vix_series)
        if rule_type == "cooldown_after_loss":
            in_scope = in_scope or row["session"] in armed
        if not spec_trigger:
            in_scope = False  # vacuous trigger imposes no scope
        protected.append(is_compliant and not in_scope)
    return protected


def _validity_ok(trace):
    for row in trace["sessions"]:
        for key in ("buy_quantity", "order_count", "names_held"):
            value = row.get(key, 0)
            if not isinstance(value, (int, float)) or value != value:
                return False
    return True


def run_experiment(protocol_path: str, out_root: str,
                   overwrite: bool = False) -> dict:
    with open(protocol_path) as handle:
        protocol = yaml.safe_load(handle)
    exp = protocol["experiment_id"]
    out_dir = os.path.join(out_root, exp)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    if os.path.exists(out_dir) and overwrite:
        import shutil

        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    chain = AuditChain()
    adj_cfg = protocol["adjudication"]
    stats_cfg = adj_cfg["bootstrap"]
    mech_cfg = protocol["mechanism"]
    bench_cfg = protocol["benchmark"]
    agent_cls = _load_agent(bench_cfg["agent"])
    names = list(bench_cfg["names"])
    starts = list(bench_cfg.get("starts", [100.0] * len(names)))
    cash = float(bench_cfg["initial_cash"])

    def write(name: str, payload) -> str:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        return path

    protocol_fp = _fingerprint(protocol)
    write("protocol.yaml", protocol)
    chain.append("PROTOCOL_FROZEN", {"protocol_fingerprint": protocol_fp})

    # ---- Diagnostic feed + BASELINE (held-out NOT built yet) ----
    diag_feed = _build_feed(protocol["feed"]["diagnostic"], names, starts)
    diag_vix = _build_vix(protocol["feed"]["diagnostic"])
    diag_eps = [list(e) for e in protocol["episodes"]["diagnostic"]]
    base_agent = agent_cls()
    base_fp = fingerprint_agent(base_agent, base_agent.identity)
    base_diag = feeds.run_segment(agent_cls(), diag_feed, 0, cash, diag_vix)
    write("base_diagnostic.json", base_diag)
    chain.append("BASE_SEALED", {"policy_fingerprint": base_fp})

    # ---- Detect mechanism on diagnostic data ----
    detector = DETECTORS[mech_cfg["failure_type"]]
    detector_kwargs = dict(mech_cfg["detector_params"])
    if mech_cfg["failure_type"] == "volatility":
        mechanism = detector(
            base_diag["sessions"], diag_vix,
            mechanism_id=f"{exp}-mech", **detector_kwargs)
    else:
        mechanism = detector(
            base_diag["sessions"],
            mechanism_id=f"{exp}-mech", **detector_kwargs)
    if mechanism is None:
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NSF",
                       reason="detector found no mechanism on diagnostic",
                       extra={})
    assert mechanism.failure_type == mech_cfg["failure_type"]
    if "expected" in mech_cfg:
        assert mechanism.failure_type == mech_cfg["expected"].lower(), \
            "detected mechanism differs from controlled expectation"
    write("mechanism.json", {
        "mechanism_id": mechanism.mechanism_id,
        "failure_type": mechanism.failure_type,
        "support": mechanism.support,
        "severity": mechanism.severity,
        "evidence_refs": list(mechanism.evidence_refs)})
    chain.append("DIAGNOSED", {"mechanism": mechanism.mechanism_id,
                               "support": mechanism.support})

    # ---- Generate + compile (diagnostic ONLY) ----
    failure_mech = FailureMechanism(
        mechanism_id=mechanism.mechanism_id,
        taxonomy=mech_cfg["taxonomy"],
        condition=tuple(mechanism.evidence_refs),
        scope_hint=dict(mech_cfg.get("scope_hint", {})),
        trigger_hint=tuple(tuple(t) for t in mech_cfg.get("trigger_hint", [])),
        evidence_refs=tuple(mechanism.evidence_refs),
        provenance={"protocol_fingerprint": protocol_fp,
                    "detector": mechanism.provenance.get("detector", "")},
    )
    generated = generate_candidates(
        mechanism, base_diag["sessions"], exp)
    families_seen = []
    for generated_item in generated:
        if not families_seen or families_seen[-1] != generated_item.family:
            families_seen.append(generated_item.family)
    assert tuple(families_seen) == eligible_families(mechanism.failure_type)
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
                       base_fp, verdict="NSF",
                       reason="no compilable candidates",
                       extra={"refused": refused})

    # ---- Provider proposal up front (metric name drives comparisons) ----
    provider = DeterministicRuleProvider()
    early_proposal = provider.propose(
        repair_id=f"{exp}-repair", diagnostic_id=f"{exp}-diagnosis",
        baseline_evaluation_id=f"{exp}-base-diag",
        baseline_fingerprint=_fingerprint(base_diag["sessions"]),
        diagnostic_state_fingerprint=failure_mech.fingerprint(),
        target_agent_identity=agent_cls().identity,
        target_agent_fingerprint=base_fp,
        hypothesis_id=failure_mech.mechanism_id,
        hypothesis_fingerprint=failure_mech.fingerprint(),
        failure_class=mech_cfg["taxonomy"],
        evidence_refs=(mechanism.mechanism_id,))
    formal_metric = early_proposal.target_metric
    chain.append("PROPOSED", {"target_metric": formal_metric})

    # ---- Shadow + verify each candidate on diagnostic ----
    target_cfg = protocol["target"]
    evaluations = []
    candidate_records = []
    rep_traces = {}
    winner_entries = {}
    rep_traces = {}
    winner_entries = {}
    for gen, spec in compiled:
        entry_id = f"mem-{gen.candidate_id}"
        from evaluation.repair.schemas import MemoryEntry
        entry = MemoryEntry(
            entry_id=entry_id,
            agent_id=agent_cls().identity.agent_id,
            spec=spec,
            source_evaluation_id=f"{exp}-base-diag",
            diagnostic_evidence=(f"{exp}:controlled",),
            provenance={"mechanism_fingerprint": failure_mech.fingerprint(),
                        "protocol_fingerprint": protocol_fp})
        shadow = MemoryConditionedAgent(
            agent_cls(), [entry], (entry.entry_id,), shadow=True)
        shadow_trace = feeds.run_segment(
            shadow, diag_feed, 0, cash, diag_vix)
        assert [s["buy_quantity"] for s in shadow_trace["sessions"]] == \
               [s["buy_quantity"] for s in base_diag["sessions"]], \
            f"shadow diverged for {gen.candidate_id}"
        served = MemoryConditionedAgent(
            agent_cls(), [entry], (entry.entry_id,))
        policy_ok = (
            served.base_policy_fingerprint() == base_fp)
        rep_trace = feeds.run_segment(served, diag_feed, 0, cash, diag_vix)
        rep_traces[gen.candidate_id] = rep_trace
        winner_entries[gen.candidate_id] = entry
        rep_traces[gen.candidate_id] = rep_trace
        winner_entries[gen.candidate_id] = entry
        base_vals = _episode_values(
            base_diag, diag_eps, target_cfg, diag_vix)
        rep_vals = _episode_values(
            rep_trace, diag_eps, target_cfg, diag_vix)
        diffs = [r["value"] - b["value"]
                 for r, b in zip(rep_vals, base_vals)]
        ci = paired_bootstrap_ci(
            diffs, seed=stats_cfg["seed"], n_boot=stats_cfg["n_boot"],
            alpha=stats_cfg["alpha"])
        fires = sum(
            1 for b, r in zip(base_diag["sessions"], rep_trace["sessions"])
            if abs(_row_qty(b) - _row_qty(r)) > 1e-9)
        mask = _protected_mask(
            base_diag,
            [tuple(c) for c in spec.to_dict()["trigger"]],
            spec.rule_type, dict(spec.rule_params),
            protocol["normal_bound"], diag_vix)
        normal_ok = all(
            abs(_row_qty(b) - _row_qty(r)) < 1e-9
            for b, r, keep in zip(base_diag["sessions"],
                                  rep_trace["sessions"], mask)
            if keep)
        evaluations.append({
            "candidate_id": gen.candidate_id, "family": gen.family,
            "params": dict(gen.params),
            "spec_fingerprint": spec.fingerprint(),
            "target_reduction": sum(diffs) / len(diffs) if diffs else 0.0,
            "ci_lower": ci["lower"], "ci_upper": ci["upper"],
            "support": mechanism.support,
            "fires": fires,
            "suppression_rate": fires / len(base_diag["sessions"]),
            "normal_preserved": bool(normal_ok),
            "final_value": rep_trace["final_value"],
            "base_final_value": base_diag["final_value"],
            "drawdown": rep_trace["max_drawdown"],
            "base_drawdown": base_diag["max_drawdown"],
            "inactivity": _inactivity(rep_trace),
            "base_inactivity": _inactivity(base_diag),
            "policy_ok": bool(policy_ok),
            "validity_ok": _validity_ok(rep_trace),
        })
        candidate_records.append({
            "candidate_id": gen.candidate_id, "family": gen.family,
            "params": dict(gen.params),
            "spec": spec.to_dict(),
            "entry_fingerprint": entry.fingerprint(),
            "target_reduction": evaluations[-1]["target_reduction"],
            "ci": {"lower": ci["lower"], "upper": ci["upper"]},
            "fires": fires})
    write("candidate_results.json", {"evaluations": evaluations})
    chain.append("EVALUATED", {"n": len(evaluations)})

    # ---- Adjudicate + FREEZE (held-out still untouched) ----
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
    freeze_path = write("freeze.json", {
        "selected_id": adjudication.selected_id,
        "spec_fingerprint": next(
            (c["spec_fingerprint"] for c in evaluations
             if c["candidate_id"] == adjudication.selected_id), ""),
        "protocol_fingerprint": protocol_fp})
    chain.append("FROZEN", {"selected": adjudication.selected_id})
    assert not os.path.exists(os.path.join(out_dir, "heldout.json")), \
        "held-out artefacts must not predate the freeze"

    # ---- Held-out: winner ONLY ----
    held_feed = _build_feed(protocol["feed"]["heldout"], names, starts)
    held_vix = _build_vix(protocol["feed"]["heldout"])
    held_eps = [list(e) for e in protocol["episodes"]["heldout"]]
    write("heldout_feed.json", {"feed": held_feed,
                                "episodes": held_eps,
                                "vix": held_vix})
    if not adjudication.selected_id:
        return _finish(out_dir, write, chain, protocol, protocol_fp,
                       base_fp, verdict="NSF",
                       reason="no admissible repair selected",
                       extra={"adjudication": "NO ADMISSIBLE REPAIR"})
    selected = next(c for c in candidate_records
                    if c["candidate_id"] == adjudication.selected_id)
    from evaluation.repair.schemas import RepairSpec
    selected_spec = RepairSpec.from_dict(selected["spec"])
    from evaluation.repair.schemas import MemoryEntry as EntryCls
    winner = EntryCls(
        entry_id=f"mem-{adjudication.selected_id}",
        agent_id=agent_cls().identity.agent_id,
        spec=selected_spec,
        source_evaluation_id=f"{exp}-base-diag",
        diagnostic_evidence=(f"{exp}:controlled",),
        provenance={"mechanism_fingerprint": failure_mech.fingerprint(),
                    "protocol_fingerprint": protocol_fp,
                    "candidate_id": adjudication.selected_id})
    served_held = MemoryConditionedAgent(
        agent_cls(), [winner], (winner.entry_id,))
    base_held = feeds.run_segment(
        agent_cls(), held_feed, 0, cash, held_vix)
    rep_held = feeds.run_segment(served_held, held_feed, 0, cash, held_vix)
    base_hvals = _episode_values(
        base_held, held_eps, target_cfg, held_vix)
    rep_hvals = _episode_values(
        rep_held, held_eps, target_cfg, held_vix)
    held_diffs = [r["value"] - b["value"]
                  for r, b in zip(rep_hvals, base_hvals)]
    held_ci = paired_bootstrap_ci(
        held_diffs, seed=stats_cfg["seed"] + 1,
        n_boot=stats_cfg["n_boot"], alpha=stats_cfg["alpha"])
    held_target_ok = (
        sum(held_diffs) / len(held_diffs) < 0 if held_diffs else False)
    held_econ_ok = (
        rep_held["final_value"] >= base_held["final_value"]
        * (1.0 - adj_cfg["tolerance_value"])
        and rep_held["max_drawdown"]
        <= base_held["max_drawdown"] + adj_cfg["tolerance_drawdown"])
    write("heldout.json", {
        "base": _trace_summary(base_held),
        "repaired": _trace_summary(rep_held),
        "held_ci": held_ci,
        "target_improved": bool(held_target_ok),
        "economics_ok": bool(held_econ_ok)})
    chain.append("HELDOUT", {"target_improved": bool(held_target_ok),
                             "economics_ok": bool(held_econ_ok)})
    admitted = bool(held_target_ok and held_econ_ok)

    result_payload = {
        "experiment": exp,
        "selected_id": adjudication.selected_id,
        "selected_family": selected["family"],
        "held_target_improved": bool(held_target_ok),
        "held_economics_ok": bool(held_econ_ok),
        "held_ci": held_ci,
        "policy_fingerprint": base_fp,
    }
    if admitted:
        winner_rep = rep_traces[adjudication.selected_id]
        winner_entry = winner_entries[adjudication.selected_id]
        comparisons = []
        seen_metrics = set()
        for window, ref_trace, val_trace in (
                ("candidate_diagnostic", base_diag, winner_rep),
                ("candidate_heldout", base_held, rep_held)):
            comparisons.append(
                (window, "adaptive_target",
                 _mean_target(ref_trace, window, diag_eps, held_eps,
                              target_cfg, diag_vix, held_vix),
                 _mean_target(val_trace, window, diag_eps, held_eps,
                              target_cfg, diag_vix, held_vix)))
            seen_metrics.add("adaptive_target")
            if formal_metric != "adaptive_target":
                comparisons.append(
                    (window, formal_metric,
                     _formal_metric_value(ref_trace, formal_metric),
                     _formal_metric_value(val_trace, formal_metric)))
                seen_metrics.add(formal_metric)
            for metric, ref_val, val_val in (
                    ("final_portfolio_value",
                     ref_trace["final_value"], val_trace["final_value"]),
                    ("max_drawdown_ratio",
                     ref_trace["max_drawdown"], val_trace["max_drawdown"]),
                    ("turnover",
                     ref_trace["turnover"], val_trace["turnover"]),
                    ("inactivity_rate",
                     _inactivity(ref_trace), _inactivity(val_trace))):
                if metric in seen_metrics:
                    continue
                seen_metrics.add(metric)
                comparisons.append((window, metric, ref_val, val_val))
        analysis = analyze_regression(
            analysis_id=f"{exp}-analysis",
            candidate_id=adjudication.selected_id,
            validation_fingerprint="pending-report",
            comparisons=tuple(comparisons),
            tolerances=())
        proposal = early_proposal
        report = ValidationReport(
            validation_id=f"{exp}-validation",
            candidate_id=adjudication.selected_id,
            candidate_fingerprint=_fingerprint(
                {"spec": selected["spec"]}),
            baseline_evaluation_id=f"{exp}-base-diag",
            baseline_fingerprint=_fingerprint(base_diag["sessions"]),
            runs=(
                ValidationRun(
                    label="candidate_diagnostic",
                    window=("DIAG", "DIAG"),
                    result_fingerprint=_fingerprint(
                        winner_rep["sessions"]),
                    metrics=_window_metrics(winner_rep)),
                ValidationRun(
                    label="candidate_heldout", window=("HELD", "HELD"),
                    result_fingerprint=_fingerprint(
                        rep_held["sessions"]),
                    metrics=_window_metrics(rep_held)),
                ValidationRun(
                    label="original_heldout", window=("HELD", "HELD"),
                    result_fingerprint=_fingerprint(
                        base_held["sessions"]),
                    metrics=_window_metrics(base_held)),
            ),
            method="control-plane", method_version="v1")
        # Rebuild analysis against the real report fingerprint, then decide.
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
                           base_fp, verdict="REJECT",
                           reason=f"formal gate refused: {reason}",
                           extra=result_payload)
        result = RepairResult(
            repair_id=f"{exp}-repair",
            proposal_fingerprint=proposal.fingerprint(),
            candidate_id=adjudication.selected_id,
            candidate_fingerprint=_fingerprint(
                {"spec": selected["spec"]}),
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
                           base_fp, verdict="REJECT",
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
            agent_cls(), [re_entry], (re_entry.entry_id,))
        assert re_served.base_policy_fingerprint() == base_fp
        re_trace = feeds.run_segment(
            re_served, diag_feed, 0, cash, diag_vix)
        assert [s["buy_quantity"] for s in re_trace["sessions"]] == \
               [s["buy_quantity"] for s in winner_rep["sessions"]]
        # Twin advancement: same observation sequence => same policy state.
        twin = MemoryConditionedAgent(
            agent_cls(), [re_entry], (re_entry.entry_id,))
        feeds.run_segment(twin, diag_feed, 0, cash, diag_vix)
        assert re_served.base_policy_fingerprint() == \
            twin.base_policy_fingerprint()
        chain.append("PERSISTED", {"reproduced": True})
        result_payload["persistence"] = "REPRODUCED"
        # Rollback.
        rolled = MemoryConditionedAgent(
            agent_cls(), [re_entry], ())
        assert rolled.base_policy_fingerprint() == base_fp
        roll_trace = feeds.run_segment(
            rolled, diag_feed, 0, cash, diag_vix)
        assert [s["buy_quantity"] for s in roll_trace["sessions"]] == \
               [s["buy_quantity"] for s in base_diag["sessions"]]
        twin_roll = MemoryConditionedAgent(
            agent_cls(), [re_entry], ())
        feeds.run_segment(twin_roll, diag_feed, 0, cash, diag_vix)
        assert rolled.base_policy_fingerprint() == \
            twin_roll.base_policy_fingerprint()
        chain.append("ROLLED_BACK", {"restored": True})
        result_payload["rollback"] = "RESTORED"
    else:
        result_payload["persistence"] = "NOT_ATTEMPTED"
        result_payload["rollback"] = "NOT_ATTEMPTED"
    return _finish(out_dir, write, chain, protocol, protocol_fp,
                   base_fp, verdict="ACCEPT",
                   reason="adaptive selection passed all gates",
                   extra=result_payload)


def _row_qty(row):
    return float(row.get("buy_quantity", 0.0) or 0.0)


def _inactivity(trace):
    sessions = trace["sessions"]
    quiet = sum(1 for s in sessions if _row_qty(s) <= 0)
    return quiet / len(sessions) if sessions else 1.0


def _trace_summary(trace):
    return {"final_value": trace["final_value"],
            "max_drawdown": trace["max_drawdown"],
            "turnover": trace["turnover"],
            "n_sessions": trace["n_sessions"]}


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


def _formal_metric_value(trace, metric_name):
    sessions = trace["sessions"]
    if metric_name == "max_post_loss_quantity":
        best, prev_neg = 0.0, False
        for row in sessions:
            qty = _row_qty(row)
            if prev_neg:
                best = max(best, qty)
            try:
                prev_neg = float(row.get("reward", 0.0)) < 0.0
            except (TypeError, ValueError):
                prev_neg = False
        return best
    if metric_name == "gross_exposure_max":
        peak = 0.0
        for row in sessions:
            notional = 0.0
            for key, qty in (row.get("quantities") or {}).items():
                price = (row.get("closes") or {}).get(key, 0.0)
                try:
                    notional += float(qty) * float(price)
                except (TypeError, ValueError):
                    continue
            peak = max(peak, notional)
        return peak
    if metric_name == "turnover":
        return trace["turnover"]
    return None


def _mean_target(trace, window, diag_eps, held_eps, target_cfg,
                 diag_vix, held_vix):
    eps = diag_eps if "diagnostic" in window else held_eps
    vix = diag_vix if "diagnostic" in window else held_vix
    values = [v["value"] for v in _episode_values(trace, eps, target_cfg,
                                                 vix)]
    return sum(values) / len(values) if values else 0.0


def _window_metrics(trace):
    return {
        "final_portfolio_value": trace["final_value"],
        "max_drawdown_ratio": trace["max_drawdown"],
        "turnover": trace["turnover"],
        "inactivity_rate": _inactivity(trace),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Adaptive repair experiments")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--out-root", default="data/adaptive_repair")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    import os as _os

    _os.chdir(args.base_dir)
    run_experiment(args.protocol, args.out_root, args.overwrite)


if __name__ == "__main__":
    main()
