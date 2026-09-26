"""V3 sequence-feature tests: schema, PIT, leakage mutations.

Covers the three mandatory mutation tests: future-trajectory change,
current-outcome change, and missingness/support honesty. Protocol
only — no model-quality assertions.
"""

import copy
import csv
import json
import os

import pytest

from evaluation.attribution import features_seq as S3
from evaluation.attribution.features import RETROSPECTIVE_OUTCOMES


@pytest.fixture()
def tiny_traj(tmp_path):
    base = str(tmp_path)
    art = os.path.join(base, "ART")
    os.makedirs(art, exist_ok=True)
    cols = ["experiment_id", "episode_id", "decision_id",
            "decision_timestamp", "instrument", "action",
            "participation_status", "forward_return_3d", "mae",
            "forward_return_1d", "mfe", "hold_return",
            "opportunity_return"]
    with open(os.path.join(art, "decision_table.csv"), "w",
              newline="") as h:
        w = csv.writer(h)
        w.writerow(cols)
        for i, ts in enumerate(
                ["2023-05-15", "2023-05-16", "2023-05-17"]):
            w.writerow(["E", "E-ep1", f"d{i}", ts, "RELIANCE:EQ", "BUY",
                        "EXECUTED", "0.01", "0.005", "0.001", "0.006",
                        "0.0", "0.0"])
    records = []
    for i, ts in enumerate(["2023-05-15", "2023-05-16", "2023-05-17"]):
        records.append({
            "decision_timestamp": ts,
            "portfolio_before": {
                "cash": 100000.0 - 1000.0 * i,
                "exposure": 0.01 * i,
                "total_equity": 100000.0 - 500.0 * i,
                "realized_pnl": 10.0 * i},
            "submitted_orders": ([
                {"side": "BUY", "quantity": 1.0}] if i else []),
            "reward": -1.0 * i})
    with open(os.path.join(art, "baseline_result.json"), "w") as h:
        json.dump({"decision_records": records}, h)
    return base


def test_allowlist_frozen_and_outcomes_excluded(tiny_traj):
    assert len(S3.SEQ_FEATURES) == 24
    assert not (set(S3.SEQ_FEATURES) & set(RETROSPECTIVE_OUTCOMES))
    assert set(S3.SEQ_PROVENANCE) == set(S3.SEQ_FEATURES)
    ds = S3.build_sequence_features(["ART"], base_dir=tiny_traj)
    assert ds["manifest"]["n_rows"] == 3
    for r in ds["rows"]:
        assert set(r["features"]) == set(S3.SEQ_FEATURES)


def test_exact_values_and_support_honesty(tiny_traj):
    ds = S3.build_sequence_features(["ART"], base_dir=tiny_traj)
    by_id = {r["keys"]["decision_id"]: r for r in ds["rows"]}
    d0 = by_id["d0"]["features"]
    assert d0["seq_n_prev_k3"] == 0.0
    assert d0["seq_buy_count_k5"] is None  # zero history stays missing
    d2 = by_id["d2"]["features"]
    assert d2["seq_n_prev_k3"] == 2.0  # only 2 prior exist: no invention
    assert d2["seq_buy_count_k3"] == 1.0  # records 0 (empty) + 1 (BUY)
    assert d2["seq_exec_freq_k3"] == pytest.approx(0.5)
    assert d2["seq_exposure_change_k3"] == pytest.approx(0.02 - 0.0)
    assert d2["seq_cash_change_k5"] == pytest.approx(-2000.0)
    assert d2["seq_reward_mean_k3"] == pytest.approx(-0.5)
    assert d2["seq_action_persistence_k3"] == pytest.approx(1.0)


def _reload_mutated(tiny_traj, mutate):
    art = os.path.join(tiny_traj, "ART")
    with open(os.path.join(art, "baseline_result.json")) as h:
        payload = json.load(h)
    with open(os.path.join(art, "decision_table.csv")) as h:
        table = list(csv.DictReader(h))
    mutate(payload, table)
    with open(os.path.join(art, "baseline_result.json"), "w") as h:
        json.dump(payload, h)
    with open(os.path.join(art, "decision_table.csv"), "w",
              newline="") as h:
        w = csv.DictWriter(h, fieldnames=table[0].keys())
        w.writeheader()
        w.writerows(table)
    return S3.build_sequence_features(["ART"], base_dir=tiny_traj)


def test_future_trajectory_mutation_leaves_past_features(tiny_traj):
    before = S3.build_sequence_features(["ART"], base_dir=tiny_traj)
    ref = {r["keys"]["decision_id"]: r["features"]
           for r in before["rows"] if r["keys"]["decision_id"] == "d1"}

    def mutate(payload, table):
        rec = payload["decision_records"][2]  # strictly after d1
        rec["portfolio_before"]["cash"] = 1.0
        rec["portfolio_before"]["exposure"] = 9.99
        rec["submitted_orders"] = [{"side": "SELL", "quantity": 99.0}]
        rec["reward"] = 12345.0
        table[2]["mae"] = "-0.99"  # future outcome

    after = _reload_mutated(tiny_traj, mutate)
    got = {r["keys"]["decision_id"]: r["features"]
           for r in after["rows"] if r["keys"]["decision_id"] == "d1"}
    assert got == ref


def test_current_outcome_mutation_leaves_history_features(tiny_traj):
    before = S3.build_sequence_features(["ART"], base_dir=tiny_traj)
    ref = {r["keys"]["decision_id"]: r["features"]
           for r in before["rows"] if r["keys"]["decision_id"] == "d2"}

    def mutate(payload, table):
        rec = payload["decision_records"][2]  # d2's own record
        rec["reward"] = 777.0  # current realised reward is post-decision
        table[2]["mae"] = "-0.50"
        table[2]["forward_return_3d"] = "-0.40"
        table[2]["hold_return"] = "0.99"

    after = _reload_mutated(tiny_traj, mutate)
    got = {r["keys"]["decision_id"]: r["features"]
           for r in after["rows"] if r["keys"]["decision_id"] == "d2"}
    assert got == ref
