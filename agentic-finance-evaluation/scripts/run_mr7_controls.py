"""M-R7 negative controls (additive): decoy repairs must be rejected.

Mirrors scripts/run_mr6_controls.py against M-R7 artefacts (M-R6 files
untouched). Three pre-registered decoys through the serving verify-only
path on the frozen diagnostic window; no held-out, no admission:
  1. opposite-side block (SELL) -> must not address BUY-side breadth;
  2. unscoped hold_all -> must be UNCOMPILABLE;
  3. total suppression (order_cap 0) -> must trip inactivity guard.
Results to data/adaptive_repair/M-R7/controls.json. An UNEXPECTED-PASS
is reported, never hidden.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

sys.path.insert(0, ".")

import yaml

from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from evaluation.repair.compiler import Uncompilable, compile_candidate

PROTOCOL_PATH = "configs/adaptive_repair/mr7_normality.yaml"
OUT_DIR = "data/adaptive_repair/M-R7"


def _load_mr7(base_dir: str):
    path = os.path.join(base_dir, "scripts", "run_mr7.py")
    name = "run_mr7_for_controls"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="M-R7 negative controls")
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()
    base_dir = args.base_dir
    R = _load_mr7(base_dir)
    with open(os.path.join(base_dir, PROTOCOL_PATH)) as handle:
        protocol = yaml.safe_load(handle)
    diag = protocol["windows"]["diagnostic"]
    # Base records reused from frozen M-R6 evidence (identical
    # deterministic trajectory; M-R7 persists sessions, not records).
    with open(os.path.join(
            base_dir, "data", "adaptive_repair", "M-R6",
            "base_diagnostic.json")) as h:
        base_records = json.load(h)["records"]
    from evaluation.repair import natural
    vix_map = natural.load_vix_map(base_dir)
    sessions = natural.adapt_records(base_records, vix_map)
    agent = R._load_agent(protocol, base_dir)
    from evaluation.diagnostics.repair.application import fingerprint_agent
    base_fp = fingerprint_agent(agent, agent.identity)
    outcomes = []
    outcomes.append(_evaluate_control(
        R, base_dir, protocol, sessions, base_records, agent, base_fp,
        control_id="control-block-sell",
        family="block_action", params={"side": "SELL"},
        taxonomy="exposure"))
    outcomes.append(_refusal_control(protocol))
    outcomes.append(_evaluate_control(
        R, base_dir, protocol, sessions, base_records, agent, base_fp,
        control_id="control-cap-zero",
        family="per_session_order_cap", params={"max_orders": 0},
        taxonomy="overtrading"))
    with open(os.path.join(base_dir, OUT_DIR, "controls.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"controls": outcomes}, handle, sort_keys=True,
                  separators=(",", ":"))
        handle.write("\n")
    for outcome in outcomes:
        print(f"{outcome['control_id']}: {outcome['verdict']} "
              f"({outcome['reason']})")


def _evaluate_control(R, base_dir, protocol, sessions, base_records, agent,
                      base_fp, control_id, family, params, taxonomy):
    from evaluation.repair.schemas import FailureMechanism, MemoryEntry
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
        spec=spec, source_evaluation_id="M-R7-base-diag",
        diagnostic_evidence=("M-R7:control",),
        provenance={"control": control_id})
    served = MemoryConditionedAgent(
        R._load_agent({**protocol, "_base_dir": base_dir}, base_dir),
        [entry], (entry.entry_id,))
    if served.base_policy_fingerprint() != base_fp:
        return {"control_id": control_id, "verdict": "ERROR",
                "reason": "policy fingerprint changed"}
    diag = protocol["windows"]["diagnostic"]
    from evaluation.baseline.runner import run_baseline
    result = run_baseline(
        served, R._build_config(protocol, f"M-R7-{control_id}", diag,
                                base_dir),
        base_dir=base_dir)
    rep_records = [r.to_dict() for r in result.decision_records]
    from evaluation.repair import natural
    rep_sessions = natural.adapt_records(
        rep_records, natural.load_vix_map(base_dir))
    base_blocks = R._block_values(sessions, 2.0, 10)
    rep_blocks = R._block_values(rep_sessions, 2.0, 10)
    diffs = [r["value"] - b["value"]
             for r, b in zip(rep_blocks, base_blocks)]
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    rep_metrics = R._trace_metrics(rep_records)
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
    main()
