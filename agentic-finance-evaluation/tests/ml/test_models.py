"""Adapter + protocol tests (no model-quality assertions)."""

import pytest

from evaluation.ml import evaluation as metrics
from evaluation.ml.diagnosis import FailureHypothesis
from evaluation.ml.experiment import Preprocessor
from evaluation.ml.falsification import (
    check_permutation_integrity, missingness_matrix, permute_labels,
)
from evaluation.ml.models.base import BaseModel
from evaluation.ml.models.logistic import LogisticModel
from evaluation.ml.models.tabpfn import (
    TabPFNModel, TabPFNUnavailable, availability_probe,
)


def _toy_rows():
    rows = []
    for i in range(8):
        rows.append({
            "keys": {"decision_id": f"d{i}",
                     "experiment_id": "E",
                     "decision_timestamp": f"2023-05-{10 + i:02d}"},
            "features": {"a": float(i), "b": None if i % 3 == 0 else 1.0,
                         "c": "x" if i % 2 else "y"},
            "outcomes": {"adverse_mae": bool(i % 2)}})
    return rows


def test_base_contract_and_shape():
    m = LogisticModel(["a", "a__missing", "b", "b__missing",
                       "c=x", "c=y"])
    assert isinstance(m, BaseModel)
    X = [[0.0, 0.0, 0.0, 0.0, 1.0, 0.0] for _ in range(4)]
    m.fit(X, [0, 1, 0, 1])
    p = m.predict_proba(X)
    assert len(p) == 4 and all(len(r) == 2 for r in p)
    assert all(0.0 <= r[1] <= 1.0 for r in p)
    assert m.metadata()["configuration"]["C"] == 1.0
    with pytest.raises(ValueError):
        LogisticModel(["a"]).predict_proba(X)


def test_logistic_deterministic():
    rows = _toy_rows()
    pre = Preprocessor(["a", "b"], ["c"], []).fit(rows)
    X = pre.transform(rows)
    y = [int(r["outcomes"]["adverse_mae"]) for r in rows]
    m1 = LogisticModel(pre.feature_names).fit(X, y)
    m2 = LogisticModel(pre.feature_names).fit(X, y)
    assert m1.predict_proba(X) == m2.predict_proba(X)
    assert m1.coefficients() and m1.intercept() == m1.intercept()


def test_tabpfn_graceful_skip_without_data_contact():
    ok, reason = availability_probe()
    assert isinstance(ok, bool) and isinstance(reason, str)
    if not ok:  # this sandbox: gated weights, no token/network
        with pytest.raises(TabPFNUnavailable):
            TabPFNModel(["a"]).fit([[0.0], [1.0]], [0, 1])
    assert "tabpfn" in TabPFNModel(["a"]).metadata()["library"]


def test_preprocessor_train_only_and_unknowns():
    rows = _toy_rows()
    pre = Preprocessor(["a", "b"], ["c"], []).fit(rows[:6])
    vec = pre.transform(
        [{"features": {"a": 99.0, "b": None, "c": "never-seen"}}])
    assert len(vec[0]) == len(pre.feature_names)
    assert all(v == v and abs(v) != float("inf") for v in vec[0])


def test_permutation_integrity_and_seed():
    y = [0, 0, 0, 1, 1, 1, 0, 1]
    a = permute_labels(y)
    b = permute_labels(y)
    assert a == b and a != y and sorted(a) == sorted(y)
    rep = check_permutation_integrity(y, a, [0, 1], [1, 0], [0, 1], [1, 0])
    assert all(rep.values())
    bad = check_permutation_integrity(y, a, [1, 1], [1, 0], [0, 1], [1, 0])
    assert bad["valid_labels_untouched"] is False


def test_missingness_matrix():
    rows = _toy_rows()
    M = missingness_matrix(rows, ["a", "b"], ["c"])
    assert len(M) == len(rows) and all(len(r) == 3 for r in M)
    assert M[0][1] == 1.0 and M[1][1] == 0.0  # b missing iff i%3==0


def test_metrics_and_single_class_guard():
    m = metrics.evaluate([0, 1, 1, 0], [0.2, 0.8, 0.6, 0.3])
    assert {"n", "positives", "prevalence", "brier", "log_loss",
            "reliability", "auroc", "auprc"} <= set(m)
    single = metrics.evaluate([1, 1, 1], [0.9, 0.8, 0.7])
    assert single["auroc"] is None and single["auprc"] is None


def test_hypothesis_roundtrip_and_unknown_rejection():
    h = FailureHypothesis(
        decision_id="d", experiment_id="E",
        decision_timestamp="2023-05-12", target="adverse_mae",
        predicted_adverse_probability=0.7, observed_target=True,
        top_contributing_features=("a",),
        model_metadata=(("model_name", "x"),),
        calibration_metadata=(("valid_brier", "0.2"),),
        feature_schema_hash="s", training_fingerprint="t")
    assert FailureHypothesis.from_dict(h.to_dict()) == h
    bad = h.to_dict()
    bad["trading_signal"] = "BUY"  # must never exist on this object
    with pytest.raises(ValueError):
        FailureHypothesis.from_dict(bad)
    assert not hasattr(h, "action") and not hasattr(h, "side")
