"""M-R4A-R1 final four-window replication (additive).

Reuses the frozen admitted M-R4A repair (mem-MR4A, max_quantity 5.0)
without modification across four pre-registered synthetic windows.
Serving path: MemoryStore -> MemoryConditionedAgent -> control plane.
Per-window paired per-episode statistics (paired bootstrap, pre-reg
seed); NO pooling across windows; NO retuning; failed windows retained.

Tolerances are protocol-specified and scale-aware: final-value check is
relative (4%), drawdown absolute (0.03) — implemented directly here
because ToleranceRule is absolute-epsilon on E1 metric scales.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, ".")

import yaml

from agents.wrappers.memory_conditioned import MemoryConditionedAgent
from benchmarks.loss_chasing import LossChasingBenchmark
from benchmarks import loss_chasing_power as feed
from benchmarks import replication_feeds as feeds
from evaluation.context.memory import MemoryStore
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.repair.gate import coverage_precheck, paired_bootstrap_ci
from evaluation.repair.schemas import MemoryEntry

PROTOCOL_PATH = "configs/controlled_repair/mr4a_r1_protocol.yaml"
OUT_DIR = "data/controlled_repair/MR4A-R1-20260930"
MR4A_ENTRY = "data/controlled_repair/MR4A-20260928/serving_entry.json"
MR4A_STORE = "data/controlled_repair/MR4A-20260928/memory_store.json"


def _resolve_mr4a_paths(base_dir: str):
    root = os.path.join(base_dir, "data", "controlled_repair")
    cands = sorted(d for d in os.listdir(root) if d.startswith("MR4A-2026")
                   and os.path.exists(os.path.join(root, d, "serving_entry.json")))
    if not cands:
        raise FileNotFoundError("no M-R4A admitted artefacts found")
    chosen = os.path.join(root, cands[0])
    return (os.path.join(chosen, "serving_entry.json"),
            os.path.join(chosen, "memory_store.json"))


def _fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_protocol(base_dir: str) -> dict:
    with open(os.path.join(base_dir, PROTOCOL_PATH)) as h:
        return yaml.safe_load(h)


def run_replication(base_dir: str, overwrite: bool = False) -> dict:
    protocol = load_protocol(base_dir)
    out_dir = os.path.join(base_dir, OUT_DIR)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    stats_cfg = protocol["statistics"]

    def write(rel: str, payload) -> str:
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")
        return path

    # ---- Frozen admitted repair (verified, never modified) ----
    entry_path, store_path = _resolve_mr4a_paths(base_dir)
    entry = MemoryEntry.from_dict(json.load(open(entry_path)))
    assert entry.entry_id == protocol["admitted_repair"]["entry_id"]
    assert entry.spec.rule_type == "max_quantity"
    assert entry.spec.rule_params == {"cap": 5.0}
    assert entry.fingerprint()[:16] == \
        protocol["admitted_repair"]["entry_fingerprint"][:16]
    store = MemoryStore.from_dict(json.load(open(store_path)))
    assert store.fingerprint()[:16] == \
        protocol["admitted_repair"]["store_fingerprint"][:16]
    from evaluation.repair import control_plane
    assert control_plane.verify_admission(store, entry)
    base_policy_fp = fingerprint_agent(
        LossChasingBenchmark(), LossChasingBenchmark().identity)

    windows_out: dict = {}
    for index, window in enumerate(("W1", "W2", "W3", "W4")):
        spec = protocol["windows"][window]
        closes = feeds.generate_closes(window)
        assert len(closes) == spec["n_sessions"]
        assert [list(e) for e in feeds.episode_ranges(window)] == \
            [list(e) for e in spec["episodes"]]
        cash = float(spec["initial_cash"])
        episodes = [list(e) for e in spec["episodes"]]

        base_trace = feed.run_segment(LossChasingBenchmark(), closes, 0, cash)
        served = MemoryConditionedAgent(LossChasingBenchmark(), [entry],
                                        (entry.entry_id,))
        assert served.base_policy_fingerprint() == base_policy_fp
        rep_trace = feed.run_segment(served, closes, 0, cash)
        def excess(trace):
            return [e["excess"] for e in feed.episode_excess(
                trace["sessions"], episodes, 5.0)]

        base_ex, rep_ex = excess(base_trace), excess(rep_trace)
        support = sum(1 for x in base_ex if x > 0)
        diffs = [r - b for r, b in zip(rep_ex, base_ex)]
        ci = paired_bootstrap_ci(
            diffs, seed=stats_cfg["seed"] + index,
            n_boot=stats_cfg["n_boot"], alpha=stats_cfg["alpha"])
        fires = sum(
            1 for b, r in zip(base_trace["sessions"], rep_trace["sessions"])
            if abs(b["buy_quantity"] - r["buy_quantity"]) > 1e-9)
        coverage = coverage_precheck(
            fires, support_cfg_min(protocol))
        ep_sessions = {t for ep in episodes for t in range(ep[0], ep[1] + 1)}
        normal_equal = all(
            abs(b["buy_quantity"] - r["buy_quantity"]) < 1e-9
            for b, r in zip(base_trace["sessions"], rep_trace["sessions"])
            if b["session"] not in ep_sessions)
        # Policy preservation: construction equality (above) plus replay
        # proof — a fresh untouched policy fed the repaired trajectory's
        # own pre-trade observations must emit the recorded BASE orders
        # exactly (compared via the wrapper's logged base fingerprints).
        # Counter state legitimately evolves from endogenous observations;
        # the mapping obs->action is what must be invariant.
        from agents.wrappers.memory_conditioned import (
            _fingerprint_orders as _fp_orders,
        )
        replay_twin = LossChasingBenchmark()
        replay_ok = True
        log = served.replay_log()
        # Pre-trade state at session t equals post-trade state at t-1
        # (no inter-session flows); session 0 uses initial capital.
        prev = {"cash": cash, "quantity": 0.0}
        for session, record in zip(rep_trace["sessions"], log):
            # Pre-trade state: carried-over cash/qty repriced at the
            # current close (exactly what run_segment observes).
            equity_pre = (prev["cash"]
                          + prev["quantity"] * session["close"])
            obs = feed.make_observation(
                session["session"], session["close"], prev["cash"],
                equity_pre,
                {"RELIANCE:EQ": prev["quantity"]}
                if prev["quantity"] > 0 else {})
            orders = [dict(o) for o in replay_twin.act(obs)]
            if _fp_orders(orders) != record["base_orders_fingerprint"]:
                replay_ok = False
                break
            prev = {"cash": session["cash"],
                    "quantity": session["quantity"]}
        policy_ok = replay_ok and len(log) == len(rep_trace["sessions"])
        # Economics with protocol tolerances.
        tol = {t["metric_name"]: t for t in protocol["tolerances"]}
        rel = tol["final_portfolio_value"]
        econ_ok = (
            rep_trace["final_value"] >=
            base_trace["final_value"] * (1.0 - rel["epsilon_relative"])
            and abs(rep_trace["max_drawdown"] - base_trace["max_drawdown"])
            <= tol["max_drawdown_ratio"]["epsilon"])
        inact_ok = not (
            rep_trace["sessions"] and
            feed.inactivity_rate(rep_trace["sessions"]) == 1.0
            and feed.inactivity_rate(base_trace["sessions"]) < 1.0)
        checks = {
            "support": support >= protocol["support"]["min_episodes_with_base_excess"],
            "ci_below_zero": ci["upper"] < 0,
            "tolerances": econ_ok,
            "inactivity": inact_ok,
            "normal_equal": normal_equal,
            "policy": policy_ok,
            "coverage": coverage["passed"],
        }
        windows_out[window] = {
            "n_sessions": len(closes),
            "n_episodes": len(episodes),
            "support": support,
            "base_excess_total": round(sum(base_ex), 2),
            "repaired_excess_total": round(sum(rep_ex), 2),
            "mean_paired_diff": round(sum(diffs) / len(diffs), 4),
            "ci": {k: (round(v, 4) if isinstance(v, float) else v)
                   for k, v in ci.items()},
            "fires": fires,
            "base_final": round(base_trace["final_value"], 2),
            "repaired_final": round(rep_trace["final_value"], 2),
            "base_drawdown": round(base_trace["max_drawdown"], 4),
            "repaired_drawdown": round(rep_trace["max_drawdown"], 4),
            "base_turnover": round(base_trace["turnover"], 2),
            "repaired_turnover": round(rep_trace["turnover"], 2),
            "base_inactivity": round(feed.inactivity_rate(base_trace["sessions"]), 4),
            "repaired_inactivity": round(feed.inactivity_rate(rep_trace["sessions"]), 4),
            "base_clamped": base_trace["clamped_sessions"],
            "checks": checks,
            "verdict": ("REPLICATED" if all(checks.values())
                        else "FAILED"),
        }
        write(f"{window}/feed.json", {
            "closes": closes, "episodes": episodes,
            "feed_fingerprint": spec["feed_fingerprint"]})
        write(f"{window}/base.json", base_trace)
        write(f"{window}/repaired.json", rep_trace)
        write(f"{window}/statistics.json", windows_out[window])
        write(f"{window}/audit.json", {
            "window": window,
            "entry_fingerprint": entry.fingerprint(),
            "policy_fingerprint": base_policy_fp,
            "support": support, "checks": checks,
        })
        print(f"{window}: support={support} diff_mean={windows_out[window]['mean_paired_diff']} "
              f"ci_below_zero={checks['ci_below_zero']} verdict={windows_out[window]['verdict']}")

    # ---- Persistence + rollback (once, on W1) ----
    closes = feeds.generate_closes("W1")
    cash = float(protocol["windows"]["W1"]["initial_cash"])
    re_store = MemoryStore.from_dict(json.load(open(store_path)))
    assert re_store.fingerprint() == store.fingerprint()
    re_entry = MemoryEntry.from_dict(json.load(open(entry_path)))
    assert re_entry.fingerprint() == entry.fingerprint()
    re_served = MemoryConditionedAgent(LossChasingBenchmark(), [re_entry],
                                       (re_entry.entry_id,))
    re_trace = feed.run_segment(re_served, closes, 0, cash)
    ref_trace = feed.run_segment(
        MemoryConditionedAgent(LossChasingBenchmark(), [entry],
                               (entry.entry_id,)), closes, 0, cash)
    persistence = (
        [s["buy_quantity"] for s in re_trace["sessions"]] ==
        [s["buy_quantity"] for s in ref_trace["sessions"]])
    rolled = MemoryConditionedAgent(LossChasingBenchmark(), [re_entry], ())
    roll_trace = feed.run_segment(rolled, closes, 0, cash)
    plain = feed.run_segment(LossChasingBenchmark(), closes, 0, cash)
    rollback = (
        [s["buy_quantity"] for s in roll_trace["sessions"]] ==
        [s["buy_quantity"] for s in plain["sessions"]])
    twin = LossChasingBenchmark()
    feed.run_segment(twin, closes, 0, cash)
    rollback_policy = rolled.base_policy_fingerprint() == fingerprint_agent(
        twin, twin.identity)

    verdicts = [windows_out[w]["verdict"] for w in ("W1", "W2", "W3", "W4")]
    if all(v == "REPLICATED" for v in verdicts):
        overall = "REPLICATION-CONSISTENT"
    elif any(v == "REPLICATED" for v in verdicts):
        overall = "PARTIALLY-CONSISTENT"
    else:
        overall = "NOT-CONSISTENT"

    consolidated = {
        "experiment": "MR4A-R1-20260930",
        "label": protocol["label"],
        "entry_fingerprint": entry.fingerprint(),
        "store_fingerprint": store.fingerprint(),
        "policy_fingerprint": base_policy_fp,
        "windows": windows_out,
        "persistence": persistence,
        "rollback": rollback,
        "rollback_policy": rollback_policy,
        "overall": overall,
    }
    write("consolidated_results.json", consolidated)
    with open(os.path.join(out_dir, "consolidated_results.csv"), "w",
              encoding="utf-8", newline="") as h:
        writer = csv.writer(h)
        writer.writerow(["window", "episodes", "support", "excess_delta",
                         "drawdown_delta", "equity_delta", "escalation_delta",
                         "policy", "behaviour", "verdict"])
        for window in ("W1", "W2", "W3", "W4"):
            r = windows_out[window]
            writer.writerow([
                window, r["n_episodes"], r["support"],
                round(r["repaired_excess_total"] - r["base_excess_total"], 2),
                round(r["repaired_drawdown"] - r["base_drawdown"], 4),
                round(r["repaired_final"] - r["base_final"], 2),
                "reduced" if r["repaired_excess_total"] < r["base_excess_total"] else "not-reduced",
                "PASS" if r["checks"]["policy"] else "FAIL",
                "PASS" if r["repaired_excess_total"] != r["base_excess_total"] else "FAIL",
                r["verdict"]])
    write("protocol.yaml", protocol)
    with open(os.path.join(base_dir, PROTOCOL_PATH), "rb") as handle:
        protocol_fp = hashlib.sha256(handle.read()).hexdigest()
    manifest = {
        "experiment": "MR4A-R1-20260930",
        "label": protocol["label"],
        "overall": overall,
        "protocol_fingerprint": protocol_fp,
        "entry_fingerprint": entry.fingerprint(),
        "store_fingerprint": store.fingerprint(),
        "policy_fingerprint": base_policy_fp,
        "persistence": persistence,
        "rollback": rollback,
    }
    manifest["manifest_fingerprint"] = _fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
    write("manifest.json", manifest)
    print(f"MR4A-R1: overall={overall} persistence={persistence} rollback={rollback}")
    return consolidated


def support_cfg_min(protocol: dict) -> int:
    return int(protocol["support"]["min_episodes_with_base_excess"])


def main() -> None:
    parser = argparse.ArgumentParser(description="M-R4A four-window replication")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run_replication(args.base_dir, args.overwrite)


if __name__ == "__main__":
    main()
