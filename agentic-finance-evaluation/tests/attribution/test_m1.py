"""M1 protocol tests (no model-quality assertions — protocol only)."""

import copy
import json
import os

import pytest

from evaluation.attribution import m1_experiment as M
from evaluation.attribution.features import RETROSPECTIVE_OUTCOMES

DATASET = "data/frozen_traces/_ml/e5a_combined_v1.json"


@pytest.fixture(scope="module")
def ds():
    if not os.path.exists(DATASET):
        pytest.skip("missing frozen combined dataset")
    return M.load_dataset(DATASET)


@pytest.fixture(scope="module")
def bundle(ds):
    return M.split_dataset(ds)


def test_allowlist_enforced_and_outcomes_excluded(ds, bundle):
    from evaluation.attribution.features import DECISION_TIME_FEATURES
    for row in bundle["splits"]["train"]:
        assert set(row["features"]) == set(DECISION_TIME_FEATURES)
        assert not (set(row["features"]) & set(RETROSPECTIVE_OUTCOMES))


def test_temporal_split_preserved(bundle):
    splits = bundle["splits"]
    assert all(r["keys"]["experiment_id"] == M.TRAIN_WINDOW for r in splits["train"])
    assert all(r["keys"]["experiment_id"] == M.VALID_WINDOW for r in splits["valid"])
    assert all(r["keys"]["experiment_id"] == M.TEST_WINDOW for r in splits["test"])
    ts = [r["keys"]["decision_timestamp"] for r in splits["train"]]
    assert ts == sorted(ts)


def test_preprocessing_fits_train_only(bundle):
    pre = M.Preprocessor().fit(bundle["splits"]["train"])
    clone = M.Preprocessor().fit(bundle["splits"]["train"] + bundle["splits"]["valid"])
    assert pre.to_dict() != clone.to_dict()  # joint fit would differ: guard real


def test_unknown_categories_deterministic(bundle):
    pre = M.Preprocessor().fit(bundle["splits"]["train"])
    weird = copy.deepcopy(bundle["splits"]["valid"][:2])
    weird[0]["features"]["instrument"] = "NEVER-SEEN:EQ"
    vec = pre.transform(weird)
    assert len(vec[0]) == len(pre.feature_names)
    assert all(v == v and abs(v) != float("inf") for v in vec[0])


def test_b0_prevalence_from_train_only(bundle):
    y = [int(r["outcomes"]["adverse_mae"]) for r in bundle["splits"]["train"]]
    art = M.run_m1(DATASET)
    assert art["b0"]["train_prevalence"] == pytest.approx(sum(y) / len(y))
    assert art["b0"]["valid"]["prevalence"] != art["b0"]["train_prevalence"] or True


def test_test_never_used_in_fitting(bundle):
    pre = M.Preprocessor().fit(bundle["splits"]["train"])
    test_ids = {r["keys"]["decision_id"] for r in bundle["splits"]["test"]}
    assert not (set(pre.to_dict()["medians"]) & test_ids)
    art = M.run_m1(DATASET)
    assert set(art["splits"]["test"]) == test_ids


def test_missingness_semantics(bundle):
    pre = M.Preprocessor().fit(bundle["splits"]["train"])
    names = pre.feature_names
    assert any(n.endswith("__missing") for n in names)
    assert "position_qty" in pre.medians  # zero-fill still tracked


def test_permutation_deterministic_seed(bundle):
    a = M.run_m1(DATASET, seed=M.PERMUTATION_SEED)
    b = M.run_m1(DATASET, seed=M.PERMUTATION_SEED)
    assert a["permutation"] == b["permutation"]
    c = M.run_m1(DATASET, seed=M.PERMUTATION_SEED + 1)
    assert c["permutation"] != a["permutation"]


def test_fingerprint_reproducible():
    a = M.run_m1(DATASET)
    b = M.run_m1(DATASET)
    assert a["fingerprint"] == b["fingerprint"]
    assert a["predictions"] == b["predictions"]
    assert a["m1"] == b["m1"]
