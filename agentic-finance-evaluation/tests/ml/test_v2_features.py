"""V2 feature tests: frozen allowlist, PIT purity, leakage guard.

Uses a hand-computable tmp fixture (no big-data dependency) for exact
PIT assertions, plus structural invariants checked on small synthetic
rows. No model-quality assertions anywhere.
"""

import csv
import json
import os

import pytest

from evaluation.attribution import features_v2 as F2
from evaluation.attribution.features import RETROSPECTIVE_OUTCOMES


@pytest.fixture()
def tiny_base(tmp_path):
    base = str(tmp_path)

    def write(rel, header, rows):
        p = os.path.join(base, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", newline="") as h:
            w = csv.writer(h)
            w.writerow(header)
            w.writerows(rows)

    write("data/processed/india/equities/nse_equity_daily.csv",
          ["observation_date", "symbol", "close", "high", "low",
           "traded_quantity"],
          [["2023-05-10", "RELIANCE", "100", "101", "99", "1000"],
           ["2023-05-11", "RELIANCE", "102", "103", "101", "1100"],
           ["2023-05-12", "RELIANCE", "101", "102", "100", "1200"]])
    write("data/processed/india/market/nse_nifty_50_daily.csv",
          ["date", "close"],
          [["2023-05-10", "1000"], ["2023-05-11", "1010"],
           ["2023-05-12", "1005"]])
    write("data/processed/india/market/nse_india_vix_daily.csv",
          ["date", "close"],
          [["2023-05-10", "12"], ["2023-05-11", "13"],
           ["2023-05-12", "12.5"]])
    write("data/processed/india/market/rbi_usd_inr_daily.csv",
          ["date", "rate"],
          [["2023-05-10", "82.0"], ["2023-05-11", "82.1"],
           ["2023-05-12", "82.2"]])
    write("data/processed/india/instruments/"
          "mcx_gold_futures_individual_contracts.csv",
          ["trade_date", "contract_symbol", "close"],
          [["2023-05-11", "GOLDAUG2023", "1900"]])
    write("data/processed/india/macro/rbi_policy_rate_events.csv",
          ["announcement_date", "rate_pct", "stance"],
          [["2023-04-06", "6.5", "withdrawal"],
           ["2023-05-20", "6.5", "withdrawal"]])
    write("data/processed/india/macro/mospi_cpi_combined_monthly.csv",
          ["observation_date", "availability_date", "cpi_index"],
          [["2023-04-30", "2023-05-12", "180.0"],
           ["2023-05-31", "2023-06-12", "181.0"]])
    write("data/processed/india/macro/mospi_iip_general_monthly.csv",
          ["observation_date", "availability_date", "iip_index"],
          [["2023-04-30", "2023-05-10", "140.0"]])

    art = os.path.join(base, "ART")
    os.makedirs(art, exist_ok=True)
    cols = ["experiment_id", "episode_id", "decision_id", "arm",
            "decision_timestamp", "instrument", "action", "quantity",
            "execution_price", "cash_before", "total_equity_before",
            "exposure_before", "agent_context_version",
            "participation_status", "attribution_status",
            "forward_return_3d", "mae", "forward_return_1d", "mfe",
            "hold_return", "opportunity_return"]
    with open(os.path.join(art, "decision_table.csv"), "w",
              newline="") as h:
        w = csv.writer(h)
        w.writerow(cols)
        w.writerow(["E", "E-ep1", "d1", "A", "2023-05-12", "RELIANCE:EQ",
                    "BUY", "1", "102", "100000", "100000", "0", "C0",
                    "EXECUTED", "DECIDABLE", "-0.005", "-0.02", "-0.001",
                    "0.001", "0.0", "0.0"])
        w.writerow(["E", "E-ep1", "d2", "A", "2023-05-13", "RELIANCE:EQ",
                    "BUY", "1", "101", "99000", "99000", "0.01", "C0",
                    "EXECUTED", "DECIDABLE", "0.002", "0.005", "0.001",
                    "0.006", "0.0", "0.0"])
    with open(os.path.join(art, "baseline_result.json"), "w") as h:
        json.dump({"decision_records": [
            {"decision_timestamp": "2023-05-12",
             "portfolio_before": {"holdings_value": 0.0,
                                  "cumulative_costs": 0.0}},
            {"decision_timestamp": "2023-05-13",
             "portfolio_before": {"holdings_value": 500.0,
                                  "cumulative_costs": 1.5}}]}, h)
    return base


def test_allowlist_frozen_exact():
    assert len(F2.DECISION_TIME_FEATURES_V2) == 23
    assert set(F2.DECISION_TIME_FEATURES_V2) == set(
        F2.NUMERIC_FEATURES_V2) | set(F2.CATEGORICAL_FEATURES_V2)
    assert not (set(F2.DECISION_TIME_FEATURES_V2)
                & set(RETROSPECTIVE_OUTCOMES))


def test_provenance_complete():
    required = {"source", "pit_rule", "derivation", "agent_observes",
                "missingness"}
    assert set(F2.FEATURE_PROVENANCE_V2) == set(
        F2.DECISION_TIME_FEATURES_V2)
    for name, prov in F2.FEATURE_PROVENANCE_V2.items():
        assert required <= set(prov), name


def test_pit_exact_values(tiny_base):
    ds = F2.build_ml_dataset_v2(["ART"], base_dir=tiny_base)
    assert ds["manifest"]["n_rows"] == 2
    by_id = {r["keys"]["decision_id"]: r for r in ds["rows"]}
    f1 = by_id["d1"]["features"]
    # strict <T: eligible closes before 05-12 are 100, 102 only
    assert f1["instrument_return_1d"] == pytest.approx(0.02)
    assert f1["instrument_return_3d"] is None
    assert f1["nifty_return_1d"] == pytest.approx(0.01)
    assert f1["usdinr_return_5d"] is None  # only 2 eligible rates
    assert f1["vix_change_5d"] is None
    assert f1["gold_return_5d"] is None
    # announcement-gated: 05-20 event must not leak
    assert f1["rbi_policy_rate_pct"] == pytest.approx(6.5)
    assert f1["rbi_stance"] == "withdrawal"
    # vintage-gated: 05-12 availability eligible ON 05-12; June not
    assert f1["latest_cpi"] == pytest.approx(180.0)
    assert f1["latest_iip"] == pytest.approx(140.0)
    assert f1["drawdown"] == pytest.approx(0.0)
    assert f1["holdings_value"] == pytest.approx(0.0)
    assert f1["cumulative_costs"] == pytest.approx(0.0)
    assert f1["active_context_version"] == "C0"
    o1 = by_id["d1"]["outcomes"]
    assert o1["adverse_mae"] is True
    assert o1["adverse_forward_3d"] is False  # -0.005 within band

    f2 = by_id["d2"]["features"]
    assert f2["instrument_return_1d"] == pytest.approx((101 - 102) / 102)
    assert f2["drawdown"] == pytest.approx(-0.01)
    assert f2["holdings_value"] == pytest.approx(500.0)
    assert by_id["d2"]["outcomes"]["adverse_mae"] is False


def test_schema_exact_and_outcomes_separate(tiny_base):
    ds = F2.build_ml_dataset_v2(["ART"], base_dir=tiny_base)
    for r in ds["rows"]:
        assert set(r["features"]) == set(F2.DECISION_TIME_FEATURES_V2)
        assert not (set(r["features"]) & set(RETROSPECTIVE_OUTCOMES))
    assert ds["manifest"]["macro_drop_threshold"] == pytest.approx(0.80)


def test_pure_helpers():
    assert F2._closes_before(
        [("2023-05-12", 5.0), ("2023-05-13", 6.0)], "2023-05-13", 5) == [5.0]
    assert F2._return([100.0, 110.0], 1) == pytest.approx(0.10)
    assert F2._return([100.0], 1) is None
    assert F2._return([0.0, 5.0], 1) is None
    assert F2._stdev_1d([100.0] * 12) == pytest.approx(0.0)
    assert F2._stdev_1d([100.0, 101.0]) is None
