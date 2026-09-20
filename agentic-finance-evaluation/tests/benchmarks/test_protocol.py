"""Protocol, manifest, F-sequence, and admissibility contracts.

Manifest consistency (pool covers sequence, budgets cover work),
F-arm stopping semantics as frozen data, and outcome-independent
temporal admissibility pinned against the shipped calendar and gold
contract files. No market episodes; small-file reads only
(calendar CSV, gold contracts). No returns inspected anywhere.
"""

import csv
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.yaml"


def _manifest():
    with open(MANIFEST_PATH) as handle:
        return yaml.safe_load(handle)


def test_manifest_freezes_required_sections():
    manifest = _manifest()
    assert manifest["protocol_revision"] == "E3-C.1"
    assert manifest["temporal"]["diagnostic_start"] == "2023-05-15"
    assert manifest["temporal"]["diagnostic_end"] == "2023-06-15"
    assert manifest["temporal"]["heldout_start"] == "2023-07-10"
    assert manifest["temporal"]["heldout_end"] == "2023-08-10"
    assert manifest["budgets"] == {
        "max_tests": 5,
        "max_repairs": 1,
        "max_validation_runs": 3,
    }
    assert manifest["environment"]["strict_pit"] is True
    assert manifest["environment"]["vintage_policy"] == "explicit"


def test_fixed_sequence_covered_by_pool_and_budget():
    manifest = _manifest()
    pool_ids = [t["test_id"] for t in manifest["candidate_pool"]]
    order = manifest["fixed_sequence"]["order"]
    assert order == [
        "T-null", "T-cost2x", "T-uni-tcs",
        "T-vintage-earliest", "T-cost0",
    ]
    assert len(set(order)) == len(order)
    assert all(tid in pool_ids for tid in order)
    assert manifest["budgets"]["max_tests"] >= len(order)
    stopping = manifest["fixed_sequence"]
    assert stopping["on_completed"] == "continue"
    assert stopping["on_invalid"] == "record and continue"
    assert stopping["on_failed"] == "record and halt"
    assert stopping["on_budget_exhausted"] == "halt"


def test_candidate_pool_uses_only_frozen_intervention_types():
    from evaluation.diagnostics.execution.interventions import (
        SUPPORTED_INTERVENTION_TYPES,
    )

    manifest = _manifest()
    for entry in manifest["candidate_pool"]:
        assert entry["intervention"]["type"] in SUPPORTED_INTERVENTION_TYPES
        assert entry["estimated_cost"] >= 0


def test_windows_have_enough_known_calendar_sessions():
    with open(
        ROOT
        / "data"
        / "processed"
        / "india"
        / "calendars"
        / "historical_calendar.csv"
    ) as handle:
        rows = list(csv.DictReader(handle))
    manifest = _manifest()
    for prefix in ("diagnostic", "heldout"):
        start = manifest["temporal"][f"{prefix}_start"]
        end = manifest["temporal"][f"{prefix}_end"]
        window = [
            r for r in rows
            if r["venue"] == "NSE_CM"
            and r["calendar_date"]
            and start <= r["calendar_date"] <= end
        ]
        known = [
            r for r in window
            if r["market_status"] in ("OPEN", "SPECIAL")
        ]
        unknown = [
            r for r in window if r["market_status"] == "UNKNOWN"
        ]
        assert len(known) >= 20
        assert unknown == []
    assert (
        manifest["temporal"]["diagnostic_end"]
        < manifest["temporal"]["heldout_start"]
    )


def test_gold_contract_present_in_both_windows_by_trade_date():
    with open(
        ROOT
        / "data"
        / "processed"
        / "india"
        / "instruments"
        / "mcx_gold_futures_individual_contracts.csv"
    ) as handle:
        rows = list(csv.DictReader(handle))
    manifest = _manifest()
    for prefix in ("diagnostic", "heldout"):
        start = manifest["temporal"][f"{prefix}_start"]
        end = manifest["temporal"][f"{prefix}_end"]
        dates = {
            r["trade_date"] for r in rows
            if r["contract_symbol"] == "GOLDAUG2023"
            and start <= r["trade_date"] <= end
        }
        assert len(dates) >= 20
