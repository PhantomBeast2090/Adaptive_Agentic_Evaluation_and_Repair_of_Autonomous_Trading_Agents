"""F3 support-structure test: pins the episodic-segregation finding.

Documents measured trace structure (BUY episode / dead gap / SELL
episode); it is a finding recorder, not a gate — the F3d verdict
(STOP before mining) follows from these numbers.
"""

import csv
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "..",
                    "data", "frozen_traces")


def _exec(exp):
    return [r for r in csv.DictReader(
        open(os.path.join(BASE, exp, "decision_table.csv")))
        if r["participation_status"] == "EXECUTED" and r["mae"]]


def test_episodic_segregation_structure():
    a = _exec("F3A-20260926")
    assert len(a) == 54
    pre = [r for r in a if r["decision_timestamp"] < "2020-02-15"]
    mid = [r for r in a
           if "2020-02-15" <= r["decision_timestamp"] <= "2020-03-01"]
    post = [r for r in a if r["decision_timestamp"] > "2020-03-01"]
    assert len(pre) == 33 and all(r["action"] == "BUY" for r in pre)
    assert mid == []  # dead gap: no executions of any kind
    assert len(post) == 21 and all(r["action"] == "SELL" for r in post)
    # balanced instruments in both episodes
    from collections import Counter
    assert set(Counter(r["instrument"] for r in pre)) == {
        "RELIANCE:EQ", "TCS:EQ", "INFY:EQ"}
    assert set(Counter(r["instrument"] for r in post)) == {
        "RELIANCE:EQ", "TCS:EQ", "INFY:EQ"}


def test_no_valid_split_with_labelled_support():
    a = _exec("F3A-20260926")
    # any VALID carved inside the gap is empty; inside episodes it
    # starves TEST or duplicates TRAIN regime — assert the gap facts
    # the F3d verdict rests on.
    gap = [r for r in a
           if "2020-01-15" <= r["decision_timestamp"] <= "2020-03-01"]
    assert gap == []
