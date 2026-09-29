"""M-R4A-R1 replication tests: feed determinism, protocol match,
structural difference, entry reuse, deliverable pins."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from benchmarks import replication_feeds as feeds

BASE = os.path.join(os.path.dirname(__file__), "..", "..")


def _protocol():
    with open(os.path.join(
            BASE, "configs", "controlled_repair",
            "mr4a_r1_protocol.yaml")) as handle:
        return yaml.safe_load(handle)


def test_feeds_deterministic_and_match_protocol():
    protocol = _protocol()
    for window in ("W1", "W2", "W3", "W4"):
        spec = protocol["windows"][window]
        assert feeds.generate_closes(window) == feeds.generate_closes(window)
        assert len(feeds.generate_closes(window)) == spec["n_sessions"]
        assert [list(e) for e in feeds.episode_ranges(window)] == \
            [list(e) for e in spec["episodes"]]
        assert feeds.initial_cash(window) == spec["initial_cash"]


def test_windows_structurally_different():
    protocol = _protocol()
    starts = {protocol["windows"][w]["start_price"]
              for w in ("W1", "W2", "W3", "W4")}
    assert starts == {100.0, 250.0, 50.0, 1000.0}
    units = {tuple(protocol["windows"][w]["unit"])
             for w in ("W1", "W2", "W3", "W4")}
    assert len(units) == 4
    counts = sorted(len(protocol["windows"][w]["episodes"])
                    for w in ("W1", "W2", "W3", "W4"))
    assert counts == [12, 12, 16, 20]


def test_admitted_entry_reused_unmodified():
    import json

    from evaluation.repair.schemas import MemoryEntry

    protocol = _protocol()
    entry = MemoryEntry.from_dict(json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4A-20260930",
        "serving_entry.json"))))
    assert entry.entry_id == protocol["admitted_repair"]["entry_id"]
    assert entry.spec.rule_type == "max_quantity"
    assert entry.spec.rule_params == {"cap": 5.0}
    assert entry.fingerprint()[:16] == \
        protocol["admitted_repair"]["entry_fingerprint"][:16]


def test_replication_deliverables_pinned():
    import json

    consolidated = json.load(open(os.path.join(
        BASE, "data", "controlled_repair", "MR4A-R1-20260930",
        "consolidated_results.json")))
    assert consolidated["overall"] == "REPLICATION-CONSISTENT"
    assert consolidated["persistence"] is True
    assert consolidated["rollback"] is True
    for window in ("W1", "W2", "W3", "W4"):
        result = consolidated["windows"][window]
        assert result["verdict"] == "REPLICATED"
        assert result["checks"]["policy"] is True
        assert result["checks"]["normal_equal"] is True
        assert result["repaired_excess_total"] < result["base_excess_total"]
        assert result["repaired_final"] >= result["base_final"] * 0.96
    import csv

    with open(os.path.join(
            BASE, "data", "controlled_repair", "MR4A-R1-20260930",
            "consolidated_results.csv")) as handle:
        rows = list(csv.DictReader(handle))
    assert [r["window"] for r in rows] == ["W1", "W2", "W3", "W4"]
    assert all(r["verdict"] == "REPLICATED" for r in rows)
