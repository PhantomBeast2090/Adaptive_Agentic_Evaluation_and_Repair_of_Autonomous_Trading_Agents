"""I1 runner: frozen MultiAssetChoice logic x 6 pre-registered threshold cells
x 2 pre-registered windows, paired by market date.

For each (window, cell): BaselineConfig identical except window dates;
agent = MultiAssetChoice(g1.yaml policy with ONLY vix_low/vix_high/
trend_min overridden per configs/choice_agent/i1_grid.yaml). Persists
per-branch frozen traces under data/frozen_traces/_i1/ plus fingerprinted
manifests recording the spec fingerprint (pre-registration proof).

Modes:
  run    -- execute all 12 branches (+ automatic C0-W1 rerun check)
  audit  -- support accounting only (no mining, no repair, no MemoryStore)

No attribution, no mining, no repair, no MemoryStore contact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

import yaml

sys.path.insert(0, ".")

from agents.choice.multi_asset import MultiAssetChoice
from evaluation.attribution.persistence import code_sha, sha256_of_file
from evaluation.baseline.config import BaselineConfig
from scripts.run_g1 import build_config as _g1_build_config

SPEC_PATH = "configs/choice_agent/i1_grid.yaml"
DESIGN_PATH = "docs/I1_IDENTIFIABILITY_DESIGN.md"
G1_POLICY = "configs/choice_agent/g1.yaml"
VIX_PATH = "data/processed/india/market/nse_india_vix_daily.csv"

MANIFEST_PATHS = [
    "configs/indian_environment.yaml",
    "configs/choice_agent/g1.yaml",
    "configs/choice_agent/i1_grid.yaml",
    "docs/I1_IDENTIFIABILITY_DESIGN.md",
    "agents/choice/policy.py",
    "agents/choice/multi_asset.py",
    "data/processed/india/calendars/historical_calendar.csv",
    "data/processed/india/equities/nse_equity_daily.csv",
    "data/processed/india/market/nse_india_vix_daily.csv",
    "data/frozen_traces/_g1/universe.json",
]

G1A_ARTEFACT = "data/frozen_traces/G1-A-20260926/baseline_result.json"


def _payload_fingerprint(path: str) -> str:
    """ID-independent behavioural payload: decision_records + metrics +
    budget_usage (canonical JSON). Full-artefact fingerprint() covers
    evaluation_id by design, so cross-experiment comparison must exclude
    identity fields (see anchor_correction_20260928 in i1_grid.yaml)."""
    with open(path) as h:
        result = json.load(h)
    return _fingerprint({
        "decision_records": result["decision_records"],
        "metrics": result["metrics"],
        "budget_usage": result["budget_usage"],
    })


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def spec_fingerprint(base_dir: str) -> str:
    h = hashlib.sha256()
    for path in (SPEC_PATH, DESIGN_PATH):
        with open(os.path.join(base_dir, path), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def load_spec(base_dir: str) -> dict:
    with open(os.path.join(base_dir, SPEC_PATH)) as h:
        return yaml.safe_load(h)


def build_cell_policy(base_policy: dict, cell: dict) -> dict:
    from agents.choice.policy import DEFAULTS, V11_DEFAULTS
    from agents.choice.multi_asset import G1_DEFAULTS
    policy = dict(base_policy)
    for key in ("vix_low", "vix_high", "trend_min"):
        policy[key] = float(cell[key])
    allowed = (set(DEFAULTS) | set(V11_DEFAULTS) | set(G1_DEFAULTS)
               | {"vix_slot", "instruments"})
    unknown = set(policy) - allowed
    if unknown:
        raise ValueError(f"policy config keys not in agent table: {unknown}")
    if not policy["vix_low"] < policy["vix_high"]:
        raise ValueError(f"cell {cell['id']}: vix_low >= vix_high")
    return policy


def build_config(experiment_id: str, start: str, end: str) -> BaselineConfig:
    return _g1_build_config(experiment_id, start, end)


def save_branch(base_dir: str, experiment_id: str, window: str, cell: dict,
                config: BaselineConfig, result_dict: dict,
                agent_params: dict, spec_fp: str,
                overwrite: bool = False) -> str:
    out_dir = os.path.join(base_dir, "data", "frozen_traces", "_i1",
                           experiment_id, window, cell["id"])
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing I1 artefact dir {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    def write(name: str, payload) -> None:
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")

    write("baseline_config.json", config.to_dict())
    write("environment_spec.json", dict(result_dict["environment_spec"]))
    write("baseline_result.json", {
        k: v for k, v in result_dict.items() if k != "environment_spec"
        and k != "config"})
    manifest = {
        "experiment_id": experiment_id,
        "window": window,
        "cell": dict(cell),
        "intervention": "threshold-cell only; policy logic/market identical",
        "agent": dict(result_dict["agent_identity"]),
        "agent_params": dict(agent_params),
        "spec_fingerprint": spec_fp,
        "result_fingerprint": result_dict["result_fingerprint"],
        "code_sha": code_sha(base_dir),
        "data_shas": {p: sha256_of_file(os.path.join(base_dir, p))
                      for p in MANIFEST_PATHS},
        "config_fingerprint": _fingerprint(config.to_dict()),
    }
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    return out_dir


def run_branch(base_dir: str, experiment_id: str, window: str, cell: dict,
               base_policy: dict, spec: dict, spec_fp: str,
               overwrite: bool) -> tuple:
    win = spec["windows"][window]
    policy = build_cell_policy(base_policy, cell)
    branch_id = f"{experiment_id}-{window}-{cell['id']}"
    config = build_config(branch_id, win["start"], win["end"])
    agent = MultiAssetChoice(policy)
    from evaluation.baseline.runner import run_baseline
    result = run_baseline(agent, config, base_dir=base_dir)
    result_dict = {
        "evaluation_id": result.evaluation_id,
        "agent_identity": {"agent_id": result.agent_identity.agent_id,
                           "version": result.agent_identity.version},
        "environment_spec": dict(result.environment_spec),
        "config": result.config.to_dict(),
        "decision_records": [r.to_dict() for r in result.decision_records],
        "metrics": [m.to_dict() for m in result.metrics],
        "budget_usage": dict(result.budget_usage),
        "result_fingerprint": result.fingerprint(),
    }
    out = save_branch(base_dir, experiment_id, window, cell, config,
                      result_dict, agent.params, spec_fp, overwrite)
    return out, result_dict["result_fingerprint"]


# ---------------------------------------------------------------- audit ----

def action_class(record: dict) -> str:
    sides = {o.get("side") for o in (record.get("submitted_orders") or [])}
    sides.discard(None)
    if not sides:
        return "HOLD"
    if sides == {"BUY"}:
        return "BUY"
    if sides == {"SELL"}:
        return "SELL"
    return "MIXED"


def load_vix(base_dir: str) -> dict:
    out = {}
    with open(os.path.join(base_dir, VIX_PATH)) as h:
        for row in csv.DictReader(h):
            out[row["date"]] = float(row["close"])
    return out


def c0_regime(vix: float) -> str:
    if vix < 15.0:
        return "LOW"
    if vix <= 25.0:
        return "MID"
    return "HIGH"


def split_of(date: str, spec: dict) -> str | None:
    for split in ("TRAIN", "VALID", "TEST"):
        for third in spec["splits"][split]:
            bounds = spec["splits"][third]
            if bounds["start"] <= date <= bounds["end"]:
                return split
    return None


def audit(base_dir: str, experiment_id: str) -> dict:
    spec = load_spec(base_dir)
    vix = load_vix(base_dir)
    cells = [c["id"] for c in spec["cells"]]
    # per (window, date): {cell: class}; per-cluster instrument sets
    grid: dict = {}
    cluster_instruments: dict = {}
    per_branch: dict = {}
    for window in ("W1", "W2"):
        for cell in spec["cells"]:
            path = os.path.join(base_dir, "data", "frozen_traces", "_i1",
                                experiment_id, window, cell["id"],
                                "baseline_result.json")
            with open(path) as h:
                result = json.load(h)
            recs = result["decision_records"]
            classes = {"BUY": 0, "SELL": 0, "MIXED": 0, "HOLD": 0}
            quantities: set = set()
            exposures = []
            exits = 0
            for rec in recs:
                cls = action_class(rec)
                classes[cls] += 1
                for o in rec.get("submitted_orders") or []:
                    quantities.add(float(o["quantity"]))
                before = rec.get("portfolio_before") or {}
                after = rec.get("portfolio_after") or {}
                bp = before.get("positions") or {}
                ap = after.get("positions") or {}
                if bp and not ap:
                    exits += 1
                eq = after.get("total_equity")
                hv = after.get("holdings_value")
                if eq:
                    exposures.append((hv or 0.0) / eq)
                key = (window, rec["decision_timestamp"])
                grid.setdefault(key, {})[cell["id"]] = cls
                inst = cluster_instruments.setdefault(key, set())
                for o in rec.get("submitted_orders") or []:
                    inst.add(o.get("instrument"))
            per_branch[(window, cell["id"])] = {
                "sessions": len(recs),
                "classes": classes,
                "quantities": sorted(quantities),
                "exposure_range": [min(exposures), max(exposures)]
                if exposures else [None, None],
                "full_exits": exits,
                "fingerprint": result["result_fingerprint"],
            }
    by_split: dict = {"TRAIN": {}, "VALID": {}, "TEST": {}}
    for (window, date), votes in grid.items():
        if len(votes) != len(cells):
            raise ValueError(f"incomplete cluster {(window, date)}: "
                             f"{len(votes)}/{len(cells)} cells")
        split = split_of(date, spec)
        if split is None:
            raise ValueError(f"date {date} outside all splits")
        by_split[split].setdefault((window, date), votes)
    report = {"per_branch": per_branch, "splits": {},
              "spec_fingerprint": spec_fingerprint(base_dir)}
    for split, clusters in by_split.items():
        contrast = {k: v for k, v in clusters.items()
                    if len(set(v.values())) > 1}
        regimes: dict = {}
        pair_counts: dict = {}
        w2 = 0
        for (window, date), votes in contrast.items():
            if window == "W2":
                w2 += 1
            regimes[c0_regime(vix[date])] = \
                regimes.get(c0_regime(vix[date]), 0) + 1
            pair_counts[tuple(sorted(set(votes.values())))] = \
                pair_counts.get(tuple(sorted(set(votes.values()))), 0) + 1
        report["splits"][split] = {
            "total_clusters": len(clusters),
            "contrast_clusters": len(contrast),
            "regime_distribution": regimes,
            "class_pair_counts": {str(k): v
                                  for k, v in pair_counts.items()},
            "w2_contrast_clusters": w2,
        }
    contrast_keys = {k for clusters in by_split.values() for k, v in clusters.items()
                   if len(set(v.values())) > 1}
    contrast_instruments: set = set()
    for key in contrast_keys:
        contrast_instruments |= cluster_instruments.get(key, set())
    report["contrast_instruments"] = sorted(contrast_instruments)
    report["w2_total_contrasts"] = sum(
        r["w2_contrast_clusters"] for r in report["splits"].values())
    gates = spec["gates"]
    checks = {
        "train>=15": report["splits"]["TRAIN"]["contrast_clusters"] >=
        gates["min_paired_contrast_train"],
        "valid>=10": report["splits"]["VALID"]["contrast_clusters"] >=
        gates["min_paired_contrast_valid"],
        "test>=20": report["splits"]["TEST"]["contrast_clusters"] >=
        gates["min_paired_contrast_test"],
        # Reject per-split segregation (e.g. TRAIN=BUY / VALID=HOLD /
        # TEST=SELL): every split needs >=2 classes in its contrasts AND at
        # least one class-pair must be shared across all three splits.
        "overlap_per_split": all(
            len({c for pair in r["class_pair_counts"] for c in eval(pair)})
            >= 2
            for r in report["splits"].values()) and bool(
            set.intersection(*[
                set(r["class_pair_counts"])
                for r in report["splits"].values()])),
        "regimes>=2": len({rg for r in report["splits"].values()
                           for rg in r["regime_distribution"]})
        >= gates["min_shared_action_regimes"],
        "instruments>=3": len(report["contrast_instruments"]) >=
        gates["min_contrast_instruments"],
        "w2>=10": report["w2_total_contrasts"] >=
        gates["min_second_window_contrasts"],
    }
    report["gate_checks"] = checks
    return report


def write_audit_md(base_dir: str, experiment_id: str, report: dict) -> str:
    lines = [f"# I1 Behavioural Support Audit — {experiment_id}",
             "",
             f"Spec fingerprint: `{report['spec_fingerprint']}`",
             "",
             "## Per-branch behaviour",
             ""]
    for (window, cell), b in sorted(report["per_branch"].items()):
        lines.append(
            f"- {window}-{cell}: sessions={b['sessions']} "
            f"classes={b['classes']} quantities={b['quantities']} "
            f"exposure={b['exposure_range']} exits={b['full_exits']} "
            f"fp=`{b['fingerprint'][:8]}…`")
    lines += ["", "## Paired contrasts (cluster = window+date)", ""]
    for split, r in report["splits"].items():
        lines.append(
            f"- {split}: clusters={r['total_clusters']} "
            f"contrasts={r['contrast_clusters']} "
            f"regimes={r['regime_distribution']} "
            f"pairs={r['class_pair_counts']} "
            f"w2={r['w2_contrast_clusters']}")
    lines += ["",
              f"Contrast instruments "
              f"({len(report['contrast_instruments'])}): "
              f"{report['contrast_instruments']}",
              f"W2 total contrasts: {report['w2_total_contrasts']}",
              "", "## Gate checks", ""]
    for name, passed in report["gate_checks"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    verdict = ("I1-SUPPORT-PASS" if all(report["gate_checks"].values())
               else "I1-SUPPORT-FAIL")
    lines += ["", f"## Verdict: {verdict}", ""]
    if verdict == "I1-SUPPORT-FAIL":
        lines += ["Branch closes permanently: no I2, no new grid, "
                  "no relaxation. No mining, no repair, MemoryStore "
                  "untouched.",
                  ""]
    else:
        lines += ["STOP: request separate mining authorisation before any "
                  "miner invocation. No repair, MemoryStore untouched.",
                  ""]
    out = os.path.join(base_dir, "docs", "I1_BEHAVIOURAL_SUPPORT_AUDIT.md")
    with open(out, "w", encoding="utf-8") as h:
        h.write("\n".join(lines))
    return out


def verify(base_dir: str, experiment_id: str, base_policy: dict,
           spec: dict, skip_anchor: bool = False) -> None:
    """Bit-identical rerun + G1-A reproduction anchor (payload-level)."""
    from evaluation.baseline.runner import run_baseline
    win = spec["windows"]["W1"]
    anchor_cell = next(c for c in spec["cells"] if c["id"] == "C0")
    policy = build_cell_policy(base_policy, anchor_cell)
    branch_id = f"{experiment_id}-W1-C0"
    rerun = run_baseline(
        MultiAssetChoice(policy),
        build_config(branch_id, win["start"], win["end"]),
        base_dir=base_dir)
    persisted = json.load(open(os.path.join(
        base_dir, "data", "frozen_traces", "_i1", experiment_id,
        "W1", "C0", "baseline_result.json")))
    if rerun.fingerprint() != persisted["result_fingerprint"]:
        raise SystemExit("I1-INFRA-FAIL: C0-W1 rerun mismatch")
    print("I1 rerun check: C0-W1 bit-identical PASS")
    if not skip_anchor:
        got = _payload_fingerprint(os.path.join(
            base_dir, "data", "frozen_traces", "_i1", experiment_id,
            "W1", "C0", "baseline_result.json"))
        want = _payload_fingerprint(os.path.join(base_dir, G1A_ARTEFACT))
        if got != want:
            raise SystemExit("I1-INFRA-FAIL: C0-W1 payload differs "
                             "from frozen G1-A")
        print("I1 reproduction anchor: C0-W1 payload == frozen G1-A PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run/audit I1 cells")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--skip-anchor", action="store_true",
                        help="skip G1-A reproduction anchor check")
    args = parser.parse_args()
    base = args.base_dir
    spec = load_spec(base)
    spec_fp = spec_fingerprint(base)
    if args.verify_only:
        with open(os.path.join(base, G1_POLICY)) as h:
            base_policy = yaml.safe_load(h)["policy"]
        verify(base, args.experiment_id, base_policy, spec,
               skip_anchor=args.skip_anchor)
        return
    if args.audit_only:
        report = audit(base, args.experiment_id)
        out = write_audit_md(base, args.experiment_id, report)
        print(f"I1 audit -> {out}")
        print(f"verdict: "
              f"{'I1-SUPPORT-PASS' if all(report['gate_checks'].values()) else 'I1-SUPPORT-FAIL'}")
        return
    with open(os.path.join(base, G1_POLICY)) as h:
        base_policy = yaml.safe_load(h)["policy"]
    fps = {}
    for window in ("W1", "W2"):
        for cell in spec["cells"]:
            out, fp = run_branch(base, args.experiment_id, window, cell,
                                 base_policy, spec, spec_fp, args.overwrite)
            print(f"I1 {args.experiment_id}-{window}-{cell['id']}: "
                  f"-> {out} fp={fp[:8]}…")
            fps[(window, cell["id"])] = fp
    verify(base, args.experiment_id, base_policy, spec,
           skip_anchor=args.skip_anchor)
    spec_dir = os.path.join(base, "data", "frozen_traces", "_i1",
                            args.experiment_id)
    with open(os.path.join(spec_dir, "spec.json"), "w",
              encoding="utf-8") as h:
        json.dump(spec, h, sort_keys=True, separators=(",", ":"))
        h.write("\n")
    print(f"I1 {args.experiment_id}: 12 branches complete")


if __name__ == "__main__":
    main()
