"""M2 protocol tests: temporal order, split identity, reproducibility."""

import pytest

from evaluation.ml import experiment as E
from evaluation.ml.persistence import fingerprint_artefacts


def _rows(win, stamps, labels):
    return [{"keys": {"decision_id": f"{win}-{s}",
                      "experiment_id": win,
                      "decision_timestamp": s},
             "features": {"a": 1.0, "c": "x"},
             "outcomes": {"adverse_mae": lab}}
            for s, lab in zip(stamps, labels)]


def _ds():
    return {"rows": (
        _rows(E.TRAIN_WINDOW, ["2023-05-15", "2023-05-16"],
              [True, False])
        + _rows(E.VALID_WINDOW, ["2023-06-01", "2023-06-02"],
                [False, True])
        + _rows(E.TEST_WINDOW, ["2023-07-01", "2023-07-02"],
                [True, True]))}


def test_temporal_split_order_and_identity():
    bundle = E.split_dataset(_ds(), "adverse_mae")
    assert {r["keys"]["experiment_id"] for r in
            bundle["splits"]["train"]} == {E.TRAIN_WINDOW}
    assert bundle["splits"]["train"][0]["keys"]["decision_timestamp"] == \
        "2023-05-15"


def test_temporal_violation_raises():
    ds = _ds()
    ds["rows"][0]["keys"]["decision_timestamp"] = "2023-08-01"
    with pytest.raises(AssertionError):
        E.split_dataset(ds, "adverse_mae")


def test_unlabelled_never_manufactured():
    ds = _ds()
    ds["rows"].append({"keys": {"decision_id": "u",
                                "experiment_id": E.TRAIN_WINDOW,
                                "decision_timestamp": "2023-05-10"},
                       "features": {"a": 1.0, "c": "x"},
                       "outcomes": {"adverse_mae": None}})
    bundle = E.split_dataset(ds, "adverse_mae")
    assert bundle["dropped_unlabelled"] == 1
    assert "u" not in bundle["splits"]["train"]


def test_logistic_cell_reproducible_and_complete():
    art1 = E.run_cell(
        _ds(), "probe", "V9", ["a"], ["c"], [],
        lambda names: __import__(
            "evaluation.ml.models.logistic", fromlist=["LogisticModel"]
        ).LogisticModel(names), target="adverse_mae")
    art2 = E.run_cell(
        _ds(), "probe", "V9", ["a"], ["c"], [],
        lambda names: __import__(
            "evaluation.ml.models.logistic", fromlist=["LogisticModel"]
        ).LogisticModel(names), target="adverse_mae")
    assert art1["status"] == "COMPLETE"
    assert art1["fingerprint"] == art2["fingerprint"]
    assert art1["permutation"]["integrity"]["train_labels_changed"] in (
        True, False)
    assert art1["missingness_only"]["valid"]["brier"] >= 0.0
    assert len(art1["hypotheses"]["valid"]) == 2
    assert len(art1["hypotheses"]["test"]) == 2


def test_blocked_cell_persists_evidence_not_predictions():
    art = E.run_cell(
        _ds(), "probe-blocked", "V9", ["a"], ["c"], [],
        lambda names: __import__(
            "evaluation.ml.models.tabpfn", fromlist=["TabPFNModel"]
        ).TabPFNModel(names), target="adverse_mae")
    if art["status"] == "BLOCKED":
        assert "predictions" not in art
        assert art["blocker"]["reason"]
        assert art["fingerprint"] == fingerprint_artefacts(
            {k: v for k, v in art.items() if k != "fingerprint"})
    else:
        pytest.skip("TabPFN backend available in this environment")
