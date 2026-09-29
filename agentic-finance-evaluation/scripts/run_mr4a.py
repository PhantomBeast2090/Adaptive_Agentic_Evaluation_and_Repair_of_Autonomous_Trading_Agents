"""M-R4A controlled power-benchmark execution (additive).

CONTROLLED-KNOWN-MECHANISM (loss-chasing power v1.1): synthetic frozen
feed, pre-registered episodes, full repair loop through the real serving
path (compile -> entry -> MemoryStore -> MemoryConditionedAgent),
paired per-episode statistics, economic/regression gates, held-out,
admission (frozen extract/adjudicate/admit), persistence, rollback.

Frozen reuse: RepairCompiler, MemoryEntry, MemoryConditionedAgent,
control plane, paired_bootstrap_ci/coverage_precheck/assemble_verification,
analyze_regression, _decide, DeterministicRuleProvider, extract_candidate,
adjudicate, MemoryStore.admit, AuditChain, LossChasingBenchmark agent.
New here: synthetic feed harness (benchmarks/loss_chasing_power.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, ".")

import yaml

from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from benchmarks.loss_chasing import LossChasingBenchmark
from benchmarks import loss_chasing_power as feed
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
from evaluation.repair.audit import AuditChain
from evaluation.repair.compiler import compile as compile_mech
from evaluation.repair.control_plane import deactivate
from evaluation.repair.gate import (
    assemble_verification,
    coverage_precheck,
    paired_bootstrap_ci,
)
from evaluation.repair.schemas import (
    FailureMechanism,
    MemoryEntry,
    RepairVerification,
)

PROTOCOL_PATH = "configs/controlled_repair/mr4a_protocol.yaml"
OUT_DIR = "data/controlled_repair/MR4A-20260930"


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_protocol(base_dir: str) -> dict:
    with open(os.path.join(base_dir, PROTOCOL_PATH)) as h:
        return yaml.safe_load(h)


def target_of(trace, episodes, normal_qty=5.0):
    excess = feed.episode_excess(trace["sessions"], episodes, normal_qty)
    return excess


def run_mr4a(base_dir: str, overwrite: bool = False) -> dict:
    protocol = load_protocol(base_dir)
    out_dir = os.path.join(base_dir, OUT_DIR)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    stats_cfg = protocol["statistics"]
    support_cfg = protocol["support"]
    chain = AuditChain()

    def write(fname: str, payload) -> str:
        path = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")
        return path

    # ---- Feed fingerprint (frozen formula) ----
    feed_spec = protocol["feed"]
    normal_qty = float(feed_spec["normal_quantity"])
    diag_closes = feed.generate_closes(8, feed_spec["start_price"])
    held_closes = feed.generate_closes(4, diag_closes[-1])
    feed_fp = _fingerprint({"unit": list(feed.UNIT_RETURNS),
                            "diag": diag_closes, "held": held_closes})
    assert feed.episode_ranges(8, 0) == protocol["episodes"]["diagnostic"]
    assert feed.episode_ranges(4, len(diag_closes)) == protocol["episodes"]["heldout"]
    diag_eps = protocol["episodes"]["diagnostic"]
    held_eps = protocol["episodes"]["heldout"]
    chain.append("FEED_FROZEN", {"feed_fingerprint": feed_fp})

    # ---- BASE runs (fresh capital each segment) ----
    def fresh_agent():
        agent = LossChasingBenchmark()
        return agent

    base = fresh_agent()
    base_fp = fingerprint_agent(base, base.identity)
    base_diag = feed.run_segment(fresh_agent(), diag_closes, 0,
                                 feed_spec["initial_cash"])
    base_held = feed.run_segment(fresh_agent(), held_closes, len(diag_closes),
                                 feed_spec["initial_cash"])
    write("base_diagnostic.json", base_diag)
    write("base_heldout.json", base_held)
    chain.append("BASE_SEALED", {"policy_fingerprint": base_fp})

    # ---- Controlled diagnosis: support gate on base excess ----
    def excess_list(trace, episodes):
        return [e["excess"] for e in feed.episode_excess(
            trace["sessions"], episodes, feed_spec["normal_quantity"])]

    base_diag_excess = excess_list(base_diag, diag_eps)
    base_held_excess = excess_list(base_held, held_eps)
    diag_support = sum(1 for x in base_diag_excess if x > 0)
    held_support = sum(1 for x in base_held_excess if x > 0)
    support_ok = (diag_support >= support_cfg["min_episodes_with_base_excess"]["diagnostic"]
                  and held_support >= support_cfg["min_episodes_with_base_excess"]["heldout"])
    chain.append("DIAGNOSED", {"diag_support": diag_support,
                               "held_support": held_support,
                               "support_ok": support_ok})
    if not support_ok:
        return _finish(out_dir, write, chain, protocol, feed_fp, base_fp,
                       verdict="NSF", reason="support gate failed",
                       extra={"diag_support": diag_support,
                              "held_support": held_support})

    mech_cfg = protocol["mechanism"]
    scope_hint = {"max_quantity_cap": protocol["repair"]["rule_params"]["cap"]}
    mechanism = FailureMechanism(
        mechanism_id=mech_cfg["id"], taxonomy=mech_cfg["taxonomy"],
        condition=(f"protocol:{mech_cfg['id']}",),
        scope_hint=scope_hint, trigger_hint=(),
        evidence_refs=(feed_fp,),
        provenance={"protocol": "mr4a", "label": protocol["label"]},
    )
    compiled = compile_mech(mechanism, "spec-MR4A")
    from evaluation.repair.compiler import Uncompilable
    assert not isinstance(compiled, Uncompilable)
    assert compiled.rule_type == protocol["repair"]["rule_type"]
    assert compiled.rule_params == protocol["repair"]["rule_params"]
    entry = MemoryEntry(
        entry_id="mem-MR4A", agent_id="loss-chasing-benchmark", spec=compiled,
        source_evaluation_id="MR4A-base-diag",
        diagnostic_evidence=("MR4A:controlled-escalation",),
        provenance={"mechanism_fingerprint": mechanism.fingerprint(),
                    "protocol": "mr4a_protocol.yaml"})
    chain.append("COMPILED", {"spec": compiled.fingerprint(),
                              "entry": entry.fingerprint()})

    # ---- SHADOW: behaviour equality + prediction record ----
    shadow = MemoryConditionedAgent(fresh_agent(), [entry],
                                    (entry.entry_id,), shadow=True)
    shadow_trace = feed.run_segment(shadow, diag_closes, 0,
                                    feed_spec["initial_cash"])
    assert [s["buy_quantity"] for s in shadow_trace["sessions"]] == \
           [s["buy_quantity"] for s in base_diag["sessions"]], \
        "shadow must reproduce base behaviour exactly"
    assert shadow.shadow_log()
    n_predicted = sum(
        1 for s in shadow.shadow_log()
        if s["predicted_fingerprint"] != s["base_orders_fingerprint"])
    chain.append("SHADOWED", {"predicted_interventions": n_predicted})

    # ---- ACTIVE serving through the memory path ----
    served = MemoryConditionedAgent(fresh_agent(), [entry],
                                    (entry.entry_id,))
    assert served.base_policy_fingerprint() == base_fp
    rep_diag = feed.run_segment(served, diag_closes, 0,
                                feed_spec["initial_cash"])
    rep_held = feed.run_segment(
        MemoryConditionedAgent(fresh_agent(), [entry], (entry.entry_id,)),
        held_closes, len(diag_closes), feed_spec["initial_cash"])
    rep_diag_excess = excess_list(rep_diag, diag_eps)
    rep_held_excess = excess_list(rep_held, held_eps)
    # Normal-session equality: outside episodes, BASE == REPAIRED.
    ep_sessions = {t for ep in diag_eps for t in range(ep[0], ep[1] + 1)}
    normal_equal = all(
        abs(b["buy_quantity"] - r["buy_quantity"]) < 1e-9
        for b, r in zip(base_diag["sessions"], rep_diag["sessions"])
        if b["session"] not in ep_sessions)
    chain.append("CONDITIONED", {"normal_equal": normal_equal,
                                 "policy_preserved": served.base_policy_fingerprint() == base_fp})
    assert normal_equal, "repair must not alter normal sessions"

    # ---- Statistics: paired per-episode excess diffs ----
    diag_diffs = [r - b for r, b in zip(rep_diag_excess, base_diag_excess)]
    held_diffs = [r - b for r, b in zip(rep_held_excess, base_held_excess)]
    diag_ci = paired_bootstrap_ci(
        diag_diffs, seed=stats_cfg["seed"], n_boot=stats_cfg["n_boot"],
        alpha=stats_cfg["alpha"])
    held_ci = paired_bootstrap_ci(
        held_diffs, seed=stats_cfg["seed"] + 1, n_boot=stats_cfg["n_boot"],
        alpha=stats_cfg["alpha"])
    fires = sum(1 for b, r in zip(base_diag["sessions"], rep_diag["sessions"])
                if abs(b["buy_quantity"] - r["buy_quantity"]) > 1e-9)
    coverage = coverage_precheck(fires, diag_support)
    ci_ok = diag_ci["upper"] < 0 and held_ci["upper"] < 0
    chain.append("GATED", {"diag_ci": diag_ci, "held_ci": held_ci,
                           "coverage": coverage, "ci_ok": ci_ok})

    # ---- Regression + decision (frozen _decide) ----
    comparisons = []
    for window, ref_trace, val_trace in (
            ("candidate_diagnostic", base_diag, rep_diag),
            ("candidate_heldout", base_held, rep_held)):
        comparisons.extend([
            (window, "mean_episode_excess",
             _mean(excess_list(ref_trace, diag_eps if "diagnostic" in window else held_eps)),
             _mean(excess_list(val_trace, diag_eps if "diagnostic" in window else held_eps))),
            (window, "max_post_loss_quantity",
             _maxq(ref_trace), _maxq(val_trace)),
            (window, "final_portfolio_value",
             ref_trace["final_value"], val_trace["final_value"]),
            (window, "max_drawdown_ratio",
             ref_trace["max_drawdown"], val_trace["max_drawdown"]),
            (window, "turnover", ref_trace["turnover"], val_trace["turnover"]),
            (window, "inactivity_rate",
             feed.inactivity_rate(ref_trace["sessions"]),
             feed.inactivity_rate(val_trace["sessions"])),
        ])
    tolerances = tuple(
        ToleranceRule(metric_name=t["metric_name"], epsilon=t["epsilon"])
        for t in protocol["targets"]["tolerances"])
    # ValidationReport with synthetic metric maps (frozen constructors).
    report = ValidationReport(
        validation_id="MR4A-validation",
        candidate_id="MR4A-candidate",
        candidate_fingerprint=_fingerprint({"spec": compiled.fingerprint()}),
        baseline_evaluation_id="MR4A-base-diag",
        baseline_fingerprint=_fingerprint(base_diag["sessions"]),
        runs=(
            ValidationRun(label="candidate_diagnostic", window=("S0000", "S0095"),
                          result_fingerprint=_fingerprint(rep_diag["sessions"]),
                          metrics=_window_metrics(rep_diag, diag_eps)),
            ValidationRun(label="candidate_heldout", window=("S0096", "S0143"),
                          result_fingerprint=_fingerprint(rep_held["sessions"]),
                          metrics=_window_metrics(rep_held, held_eps)),
            ValidationRun(label="original_heldout", window=("S0096", "S0143"),
                          result_fingerprint=_fingerprint(base_held["sessions"]),
                          metrics=_window_metrics(base_held, held_eps)),
        ),
        method="control-plane", method_version="v1")
    analysis = analyze_regression(
        analysis_id="MR4A-analysis", candidate_id="MR4A-candidate",
        validation_fingerprint=report.fingerprint(),
        comparisons=tuple(comparisons), tolerances=tolerances)
    decision, reason = _decide(
        report=report, analysis=analysis,
        target_metric="mean_episode_excess",
        target_direction=ExpectedDirection.DECREASE)
    chain.append("DECIDED", {"decision": str(decision), "reason": reason})

    if decision == RepairDecision.ACCEPTED and ci_ok and coverage["passed"]:
        verdict = "ACCEPT"
    elif decision == RepairDecision.REJECTED:
        verdict = "REJECT"
    else:
        verdict = "NSF"

    result_payload = {
        "experiment": "MR4A-20260930", "verdict": verdict,
        "support": {"diag": diag_support, "held": held_support},
        "diag_ci": diag_ci, "held_ci": held_ci,
        "coverage": {"fires": fires, "passed": coverage["passed"]},
        "decision": str(decision), "reason": reason,
        "policy_fingerprint": base_fp,
        "economics": {
            "diag_final": [base_diag["final_value"], rep_diag["final_value"]],
            "held_final": [base_held["final_value"], rep_held["final_value"]],
            "diag_dd": [base_diag["max_drawdown"], rep_diag["max_drawdown"]],
            "held_dd": [base_held["max_drawdown"], rep_held["max_drawdown"]],
        },
    }
    if verdict == "ACCEPT":
        provider = DeterministicRuleProvider()
        proposal = provider.propose(
            repair_id="MR4A-repair", diagnostic_id="MR4A-diagnosis",
            baseline_evaluation_id="MR4A-base-diag",
            baseline_fingerprint=_fingerprint(base_diag["sessions"]),
            diagnostic_state_fingerprint=mechanism.fingerprint(),
            target_agent_identity=fresh_agent().identity,
            target_agent_fingerprint=base_fp,
            hypothesis_id=mechanism.mechanism_id,
            hypothesis_fingerprint=mechanism.fingerprint(),
            failure_class=mech_cfg["taxonomy"],
            evidence_refs=(feed_fp, mechanism.fingerprint()))
        result = RepairResult(
            repair_id="MR4A-repair",
            proposal_fingerprint=proposal.fingerprint(),
            candidate_id="MR4A-candidate",
            candidate_fingerprint=_fingerprint({"spec": compiled.fingerprint()}),
            validation_fingerprint=report.fingerprint(),
            analysis_fingerprint=analysis.fingerprint(),
            decision=RepairDecision.ACCEPTED, reason=reason,
            suggested_stopping=None, method="control-plane",
            method_version="v1")
        candidate_ctx = extract_candidate(
            proposal=proposal, result=result, report=report, analysis=analysis)
        store = MemoryStore(store_id="MR4A-store", entries=())
        validated, admission = adjudicate(
            candidate=candidate_ctx, result=result, report=report,
            analysis=analysis, store=store, proposal=proposal)
        assert admission.decision is AdmissionDecision.ADMITTED, \
            f"admission refused: {admission}"
        store = store.admit(validated, admission)
        chain.append("ADMITTED", {"store": store.fingerprint()})
        serving = MemoryEntry(
            entry_id=entry.entry_id, agent_id=entry.agent_id, spec=entry.spec,
            source_evaluation_id=entry.source_evaluation_id,
            diagnostic_evidence=entry.diagnostic_evidence,
            priority=entry.priority, sequence=entry.sequence,
            provenance={**dict(entry.provenance),
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
        re_served = MemoryConditionedAgent(
            fresh_agent(), [re_entry], (re_entry.entry_id,))
        # Construction-time policy equality (fresh-vs-fresh).
        assert re_served.base_policy_fingerprint() == base_fp
        re_trace = feed.run_segment(re_served, diag_closes, 0,
                                    feed_spec["initial_cash"])
        assert [s["buy_quantity"] for s in re_trace["sessions"]] == \
               [s["buy_quantity"] for s in rep_diag["sessions"]]
        # Post-run: policy state must match a twin advanced through the
        # identical session sequence (twin semantics for stateful
        # policies); served ran diag+heldout, so a diag-only twin is used.
        twin = MemoryConditionedAgent(fresh_agent(), [re_entry],
                                      (re_entry.entry_id,))
        feed.run_segment(twin, diag_closes, 0, feed_spec["initial_cash"])
        assert re_served.base_policy_fingerprint() == \
            twin.base_policy_fingerprint()
        chain.append("PERSISTED", {"reproduced": True})
        result_payload["persistence"] = "REPRODUCED"
        # Rollback.
        rolled = MemoryConditionedAgent(fresh_agent(), [re_entry], ())
        assert rolled.base_policy_fingerprint() == base_fp
        roll_trace = feed.run_segment(rolled, diag_closes, 0,
                                      feed_spec["initial_cash"])
        assert [s["buy_quantity"] for s in roll_trace["sessions"]] == \
               [s["buy_quantity"] for s in base_diag["sessions"]]
        # Twin semantics: deactivated policy evolves exactly like an
        # untouched agent over the same sessions.
        plain_twin = fresh_agent()
        feed.run_segment(plain_twin, diag_closes, 0,
                         feed_spec["initial_cash"])
        assert rolled.base_policy_fingerprint() == fingerprint_agent(
            plain_twin, plain_twin.identity)
        chain.append("ROLLED_BACK", {"restored": True})
        result_payload["rollback"] = "RESTORED"
    else:
        result_payload["persistence"] = "NOT_ATTEMPTED"
        result_payload["rollback"] = "NOT_ATTEMPTED"
    return _finish(out_dir, write, chain, protocol, feed_fp, base_fp,
                   verdict=verdict, reason=reason, extra=result_payload)


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _maxq(trace):
    return max((s["buy_quantity"] for s in trace["sessions"]), default=0.0)


def _window_metrics(trace, episodes, normal_qty=5.0):
    excess = [e["excess"] for e in feed.episode_excess(
        trace["sessions"], episodes, normal_qty)]
    return {
        "mean_episode_excess": _mean(excess),
        "max_post_loss_quantity": _maxq(trace),
        "final_portfolio_value": trace["final_value"],
        "max_drawdown_ratio": trace["max_drawdown"],
        "turnover": trace["turnover"],
        "inactivity_rate": feed.inactivity_rate(trace["sessions"]),
    }


def _finish(out_dir, write, chain, protocol, feed_fp, base_fp, verdict,
            reason, extra):
    payload = {"experiment": "MR4A-20260930", "verdict": verdict,
               "reason": reason, "policy_fingerprint": base_fp,
               "feed_fingerprint": feed_fp, **extra}
    write("result.json", payload)
    write("audit.json", chain.to_list())
    manifest = {"experiment": "MR4A-20260930",
                "label": protocol["label"], "verdict": verdict,
                "protocol_fingerprint": _fingerprint(protocol),
                "feed_fingerprint": feed_fp,
                "policy_fingerprint": base_fp}
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    print(f"MR4A-20260930: verdict={verdict} reason={reason}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="M-R4A power benchmark")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run_mr4a(args.base_dir, args.overwrite)


def main_entry():
    main()


if __name__ == "__main__":
    main_entry()
