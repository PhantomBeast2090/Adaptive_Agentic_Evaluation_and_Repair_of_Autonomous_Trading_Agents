"""I2 runner: outcome-blind support construction over candidate family K0..K3.

Y-FIREWALL: this module must never import the outcome-attribution package,
the ML-diagnosis package, or the context-memory package (enforced by
tests/agents/test_i2_branches.py::test_y_firewall). Outcome labels
(MAE, forward returns, PnL, failure labels, mined conditions) are not
computed or consulted anywhere in this file. Allowed: frozen agent logic,
baseline config/runner (measurement only), stdlib hashing.

Modes (per --candidate K0|K1|K2|K3):
  --run         execute missing branches for the candidate (K0: nothing to
                run; traces reused read-only from frozen I1 evidence)
  --verify-only re-execute one new branch + C0-W1 anchor payload check
  --audit-only  support accounting + gate verdict (behavioural only)

K1 traces: I1 C0..C5 reused from data/frozen_traces/_i1/I1-20260928 (frozen,
read-only); C06..C17 persisted under data/frozen_traces/_i2/<exp>/.
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

from agents.choice.multi_asset import G1_INSTRUMENTS, MultiAssetChoice
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.budget import EvaluationBudget

SPEC_PATH = "configs/choice_agent/i2_grid.yaml"
DESIGN_PATH = "docs/I2_IDENTIFIABILITY_DESIGN.md"
G1_POLICY = "configs/choice_agent/g1.yaml"
VIX_PATH = "data/processed/india/market/nse_india_vix_daily.csv"
I1_EXP = "I1-20260928"
G1A_ARTEFACT = "data/frozen_traces/G1-A-20260926/baseline_result.json"

MANIFEST_PATHS = [
    "configs/indian_environment.yaml",
    "configs/choice_agent/g1.yaml",
    "configs/choice_agent/i1_grid.yaml",
    "configs/choice_agent/i2_grid.yaml",
    "docs/I1_IDENTIFIABILITY_DESIGN.md",
    "docs/I2_IDENTIFIABILITY_DESIGN.md",
    "agents/choice/policy.py",
    "agents/choice/multi_asset.py",
    "data/processed/india/calendars/historical_calendar.csv",
    "data/processed/india/equities/nse_equity_daily.csv",
    "data/processed/india/market/nse_india_vix_daily.csv",
    "data/frozen_traces/_g1/universe.json",
]


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256_of_file(path: str) -> str:
    with open(path, "rb") as h:
        return hashlib.sha256(h.read()).hexdigest()


def spec_fingerprint(base_dir: str) -> str:
    h = hashlib.sha256()
    for path in (SPEC_PATH, DESIGN_PATH):
        with open(os.path.join(base_dir, path), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def load_spec(base_dir: str) -> dict:
    with open(os.path.join(base_dir, SPEC_PATH)) as h:
        return yaml.safe_load(h)


def all_cells(spec: dict) -> dict:
    return {c["id"]: c for c in spec["i1_cells"] + spec["completion_cells"]}


def candidate_cells(spec: dict, candidate: str) -> list:
    names = spec["candidates"][candidate]["cells"]
    cells = all_cells(spec)
    return [cells[n] for n in names]


def candidate_windows(spec: dict, candidate: str) -> list:
    return list(spec["candidates"][candidate]["windows"])


def candidate_test_key(spec: dict, candidate: str) -> str:
    return spec["candidates"][candidate]["test"]


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
    return BaselineConfig(
        evaluation_id=experiment_id,
        start_date=start,
        end_date=end,
        universe={
            "nse_equity": [i.split(":")[0] + ":EQ" for i in G1_INSTRUMENTS],
            "mcx_gold": ["GOLDAUG2023"],
        },
        transaction_cost_bps=5.0,
        initial_cash=100000.0,
        strict_pit=True,
        vintage_policy="explicit",
        budget=EvaluationBudget(
            max_episodes=10, max_tests=None, max_repairs=None,
            max_validation_runs=None, max_runtime=None),
        seed=None,
    )


def trace_path(base_dir: str, experiment_id: str, window: str,
               cell_id: str) -> str:
    """I1 cells resolve to frozen I1 evidence (read-only); new cells to _i2."""
    if cell_id in ("C0", "C1", "C2", "C3", "C4", "C5"):
        return os.path.join(base_dir, "data", "frozen_traces", "_i1", I1_EXP,
                            window, cell_id, "baseline_result.json")
    return os.path.join(base_dir, "data", "frozen_traces", "_i2",
                        experiment_id, window, cell_id,
                        "baseline_result.json")


def save_branch(base_dir: str, experiment_id: str, candidate: str,
                window: str, cell: dict, config: BaselineConfig,
                result_dict: dict, agent_params: dict, spec_fp: str,
                overwrite: bool = False) -> str:
    out_dir = os.path.join(base_dir, "data", "frozen_traces", "_i2",
                           experiment_id, window, cell["id"])
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing I2 artefact dir {out_dir}")
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
        "candidate": candidate,
        "window": window,
        "cell": dict(cell),
        "intervention": "threshold-cell only; policy logic/market identical",
        "agent": dict(result_dict["agent_identity"]),
        "agent_params": dict(agent_params),
        "spec_fingerprint": spec_fp,
        "result_fingerprint": result_dict["result_fingerprint"],
        "data_shas": {p: _sha256_of_file(os.path.join(base_dir, p))
                      for p in MANIFEST_PATHS},
        "config_fingerprint": _fingerprint(config.to_dict()),
    }
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    return out_dir


def run_branch(base_dir: str, experiment_id: str, candidate: str,
               window: str, cell: dict, base_policy: dict, spec: dict,
               spec_fp: str, overwrite: bool) -> tuple:
    win = spec["windows"][window]
    policy = build_cell_policy(base_policy, cell)
    branch_id = f"{experiment_id}-{window}-{cell['id']}"
    config = build_config(branch_id, win["start"], win["end"])
    result = run_baseline(MultiAssetChoice(policy), config, base_dir=base_dir)
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
    out = save_branch(base_dir, experiment_id, candidate, window, cell,
                      config, result_dict, _params_of(policy),
                      spec_fp, overwrite)
    return out, result_dict["result_fingerprint"]


def _params_of(policy: dict) -> dict:
    return dict(MultiAssetChoice(policy).params)


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


def split_of(date: str, spec: dict, test_key: str) -> str | None:
    test_thirds = spec["splits"][test_key]
    for split, thirds in (("TRAIN", spec["splits"]["TRAIN"]),
                          ("VALID", spec["splits"]["VALID"]),
                          ("TEST", test_thirds)):
        for third in thirds:
            bounds = spec["splits"][third]
            if bounds["start"] <= date <= bounds["end"]:
                return split
    return None


def audit(base_dir: str, experiment_id: str, candidate: str) -> dict:
    spec = load_spec(base_dir)
    cells = candidate_cells(spec, candidate)
    windows = candidate_windows(spec, candidate)
    test_key = candidate_test_key(spec, candidate)
    vix = load_vix(base_dir)
    grid: dict = {}
    cluster_instruments: dict = {}
    per_branch: dict = {}
    for window in windows:
        for cell in cells:
            path = trace_path(base_dir, experiment_id, window, cell["id"])
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
    n_cells = len(cells)
    by_split: dict = {"TRAIN": {}, "VALID": {}, "TEST": {}}
    for (window, date), votes in grid.items():
        if len(votes) != n_cells:
            raise ValueError(f"incomplete cluster {(window, date)}: "
                             f"{len(votes)}/{n_cells} cells")
        split = split_of(date, spec, test_key)
        if split is None:
            raise ValueError(f"date {date} outside all splits")
        by_split[split].setdefault((window, date), votes)
    report = {"candidate": candidate, "per_branch": per_branch,
              "splits": {},
              "spec_fingerprint": spec_fingerprint(base_dir)}
    for split, clusters in by_split.items():
        contrast = {k: v for k, v in clusters.items()
                    if len(set(v.values())) > 1}
        regimes: dict = {}
        pair_counts: dict = {}
        w2 = 0
        for (window, date), votes in contrast.items():
            if window in ("W2", "W2E"):
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
    contrast_keys = {k for clusters in by_split.values()
                     for k, v in clusters.items()
                     if len(set(v.values())) > 1}
    ci: set = set()
    for key in contrast_keys:
        ci |= cluster_instruments.get(key, set())
    report["contrast_instruments"] = sorted(ci)
    report["w2_total_contrasts"] = sum(
        r["w2_contrast_clusters"] for r in report["splits"].values())
    gates = spec["gates"]
    shared = set.intersection(*[set(r["class_pair_counts"])
                                for r in report["splits"].values()]) \
        if all(report["splits"].values()) else set()
    report["shared_pairs"] = sorted(shared)
    checks = {
        "train>=15": report["splits"]["TRAIN"]["contrast_clusters"] >=
        gates["min_paired_contrast_train"],
        "valid>=10": report["splits"]["VALID"]["contrast_clusters"] >=
        gates["min_paired_contrast_valid"],
        "test>=20": report["splits"]["TEST"]["contrast_clusters"] >=
        gates["min_paired_contrast_test"],
        "overlap_per_split": all(
            len({c for pair in r["class_pair_counts"]
                 for c in eval(pair)}) >= 2
            for r in report["splits"].values()) and bool(shared),
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


def _payload_fingerprint(path: str) -> str:
    with open(path) as h:
        result = json.load(h)
    return _fingerprint({
        "decision_records": result["decision_records"],
        "metrics": result["metrics"],
        "budget_usage": result["budget_usage"],
    })


def verify(base_dir: str, experiment_id: str, candidate: str,
           base_policy: dict, spec: dict) -> None:
    """Bit-identical rerun of one I2-executed branch + C0-W1 anchor."""
    cells = candidate_cells(spec, candidate)
    windows = candidate_windows(spec, candidate)
    new = [c for c in cells if c["id"] not in
           ("C0", "C1", "C2", "C3", "C4", "C5")]
    if new:
        probe = new[0]
        window = windows[0]
        policy = build_cell_policy(base_policy, probe)
        branch_id = f"{experiment_id}-{window}-{probe['id']}"
        win = spec["windows"][window]
        rerun = run_baseline(MultiAssetChoice(policy),
                             build_config(branch_id, win["start"],
                                          win["end"]), base_dir=base_dir)
        persisted = json.load(open(os.path.join(
            base_dir, "data", "frozen_traces", "_i2", experiment_id,
            window, probe["id"], "baseline_result.json")))
        if rerun.fingerprint() != persisted["result_fingerprint"]:
            raise SystemExit("I2-INFRA-FAIL: rerun fingerprint mismatch")
        print(f"I2 rerun check: {window}-{probe['id']} bit-identical PASS")
    got = _payload_fingerprint(trace_path(base_dir, experiment_id, "W1",
                                          "C0"))
    want = _payload_fingerprint(os.path.join(base_dir, G1A_ARTEFACT))
    if got != want:
        raise SystemExit("I2-INFRA-FAIL: C0-W1 payload differs from G1-A")
    print("I2 reproduction anchor: C0-W1 payload == frozen G1-A PASS")


def write_audit_md(base_dir: str, experiment_id: str, candidate: str,
                   report: dict) -> str:
    lines = [f"# I2 Behavioural Support Audit — {experiment_id} ({candidate})",
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
              f"Shared pairs across splits: {report['shared_pairs']}",
              "", "## Gate checks", ""]
    for name, passed in report["gate_checks"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    test_pairs = report["splits"]["TEST"]["class_pair_counts"]
    verdict = ("I2-SUPPORT-PASS" if all(report["gate_checks"].values())
               else "I2-SUPPORT-FAIL")
    lines += ["", f"## Verdict: {verdict}", ""]
    if verdict == "I2-SUPPORT-PASS" and len(test_pairs) == 1:
        lines += ["SINGLE-PAIR WATCH: TEST passes count with only one "
                  "behavioural pair — STOP and consult human before any "
                  "mining (no automatic mining).",
                  ""]
    if verdict == "I2-SUPPORT-FAIL":
        lines += ["No mining, no repair, no memory admission.",
                  ""]
    out = os.path.join(base_dir, "docs", "I2_BEHAVIOURAL_SUPPORT_AUDIT.md")
    with open(out, "w", encoding="utf-8") as h:
        h.write("\n".join(lines))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run/audit I2 candidates")
    parser.add_argument("--candidate", choices=["K0", "K1", "K2", "K3"],
                        required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    base = args.base_dir
    spec = load_spec(base)
    spec_fp = spec_fingerprint(base)
    with open(os.path.join(base, G1_POLICY)) as h:
        base_policy = yaml.safe_load(h)["policy"]
    if args.verify_only:
        verify(base, args.experiment_id, args.candidate, base_policy, spec)
        return
    if args.audit_only:
        report = audit(base, args.experiment_id, args.candidate)
        for split, r in report["splits"].items():
            print(f"{args.candidate} {split}: "
                  f"{r['contrast_clusters']}/{r['total_clusters']} "
                  f"{r['regime_distribution']}")
        print(f"verdict: "
              f"{'I2-SUPPORT-PASS' if all(report['gate_checks'].values()) else 'I2-SUPPORT-FAIL'}")
        return
    # --run: execute only branches not served by frozen I1 evidence
    i1_ids = {"C0", "C1", "C2", "C3", "C4", "C5"}
    for window in candidate_windows(spec, args.candidate):
        for cell in candidate_cells(spec, args.candidate):
            if cell["id"] in i1_ids and window in ("W1", "W2"):
                continue  # frozen I1 evidence reused read-only
            out, fp = run_branch(base, args.experiment_id, args.candidate,
                                 window, cell, base_policy, spec, spec_fp,
                                 args.overwrite)
            print(f"I2 {args.experiment_id}-{window}-{cell['id']}: "
                  f"-> {out} fp={fp[:8]}…")
    verify(base, args.experiment_id, args.candidate, base_policy, spec)
    print(f"I2 {args.experiment_id} {args.candidate}: execution complete")


if __name__ == "__main__":
    main()
