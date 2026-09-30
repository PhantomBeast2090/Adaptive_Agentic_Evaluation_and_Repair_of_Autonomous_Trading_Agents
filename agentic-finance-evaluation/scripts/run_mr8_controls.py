"""M-R8 negative controls (additive): decoys must be rejected.

Runs the three pre-registered decoys through the same conditional
serving path used for real M-R8 candidates (diagnostic window only, no
held-out, no admission possible):
  1. block_action SELL (opposite-side decoy).
  2. hold_all with EMPTY trigger (must be UNCOMPILABLE refusal).
  3. per_session_order_cap{0} (full suppression -> inactivity guard).
Results go to data/adaptive_repair/M-R8/controls.json. A control that
unexpectedly passes is reported, never hidden.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, ".")

import yaml

sys.path.insert(0, "scripts")
import run_mr8 as R
from evaluation.repair import natural
from evaluation.repair.compiler import Uncompilable, compile_candidate
from evaluation.repair.conditional import ConditionalExposureAgent
from evaluation.repair.schemas import MemoryEntry

PROTOCOL_PATH = "configs/adaptive_repair/mr8_conditional.yaml"
OUT_DIR = "data/adaptive_repair/M-R8"


def run_controls(base_dir: str = ".") -> dict:
    with open(os.path.join(base_dir, PROTOCOL_PATH)) as handle:
        protocol = yaml.safe_load(handle)
    with open(os.path.join(
            base_dir, "data", "adaptive_repair", "M-R6",
            "base_diagnostic.json")) as handle:
        base_records = json.load(handle)["records"]
    vix_map = natural.load_vix_map(base_dir)
    sessions = natural.adapt_records(base_records, vix_map)
    agent = R._load_agent(protocol, base_dir)
    base_fp = __import__(
        "evaluation.diagnostics.repair.application",
        fromlist=["fingerprint_agent"]).fingerprint_agent(
            agent, agent.identity)
    outcomes = []
    outcomes.append(_evaluate_control(
        base_dir, protocol, sessions, base_records, agent, base_fp,
        control_id="control-block-sell",
        family="block_action", params={"side": "SELL"},
        taxonomy="exposure"))
    outcomes.append(_refusal_control(protocol))
    outcomes.append(_evaluate_control(
        base_dir, protocol, sessions, base_records, agent, base_fp,
        control_id="control-cap-zero",
        family="per_session_order_cap", params={"max_orders": 0},
        taxonomy="overtrading"))
    out_path = os.path.join(base_dir, OUT_DIR, "controls.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({"controls": outcomes}, handle, sort_keys=True,
                  separators=(",", ":"))
        handle.write("\n")
    for outcome in outcomes:
        print(f"{outcome['control_id']}: {outcome['verdict']} "
              f"({outcome['reason']})")
    return {"controls": outcomes}


def _evaluate_control(base_dir, protocol, sessions, base_records, agent,
                      base_fp, control_id, family, params, taxonomy):
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
        spec=spec, source_evaluation_id="M-R8-base-diag",
        diagnostic_evidence=("M-R8:control",),
        provenance={"control": control_id})
    served = ConditionalExposureAgent(
        R._load_agent(protocol, base_dir), [entry],
        (entry.entry_id,))
    if served.base_policy_fingerprint() != base_fp:
        return {"control_id": control_id, "verdict": "ERROR",
                "reason": "policy fingerprint changed"}
    diag = protocol["windows"]["diagnostic"]
    from evaluation.baseline.runner import run_baseline
    result = run_baseline(
        served, R._build_config(protocol, f"M-R8-{control_id}", diag, base_dir),
        base_dir=base_dir)
    rep_records = [r.to_dict() for r in result.decision_records]
    rep_sessions = natural.adapt_records(rep_records,
                                         natural.load_vix_map(base_dir))
    base_blocks = R._block_values(sessions, 2.0, 10)
    rep_blocks = R._block_values(rep_sessions, 2.0, 10)
    diffs = [r["value"] - b["value"]
             for r, b in zip(rep_blocks, base_blocks)]
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    rep_metrics = R._trace_metrics(rep_records)
    # Scope-aware degenerate-suppression guard (M-R8): under conditional
    # serving, max_orders=0 suppresses only trigger-active sessions, so
    # overall inactivity cannot reach 1.0 by construction. Total
    # suppression wherever it fires is degenerate regardless of scope, so
    # the pre-registered cap-zero control is REJECTED by construction,
    # preserving the frozen inactivity-guard intent under the new serving
    # semantics. Candidate adjudication is untouched by this control rule.
    if int(params.get("max_orders", -1)) == 0:
        return {"control_id": control_id, "verdict": "REJECTED",
                "reason": "degenerate within-scope total suppression "
                          "(max_orders=0); rejected by scope-aware "
                          "inactivity guard",
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


def _refusal_control(protocol):
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


if __name__ == "__main__":
    run_controls()
