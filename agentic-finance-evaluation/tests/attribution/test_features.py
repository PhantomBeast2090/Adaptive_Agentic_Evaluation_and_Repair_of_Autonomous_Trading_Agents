"""Tests for the canonical PIT feature builder (no model fitting here)."""

import json
import os

import pytest

from evaluation.attribution import features as F

ARTEFACTS = [
    "data/frozen_traces/E5A-deterministic-attribution-20260926",
    "data/frozen_traces/E5A-window2-20260926",
    "data/frozen_traces/E5A-window3-20260926",
    "data/frozen_traces/E5A-highvix-20260926",
]
BOUNDS = {
    "E5A-deterministic-attribution-20260926": {
        "start": "2023-05-15", "end": "2023-06-15"},
    "E5A-window2-20260926": {"start": "2023-06-16", "end": "2023-07-15"},
    "E5A-window3-20260926": {"start": "2023-07-17", "end": "2023-08-15"},
    "E5A-highvix-20260926": {"start": "2020-03-17", "end": "2020-04-15"},
}


@pytest.fixture(scope="module")
def dataset():
    for a in ARTEFACTS:
        if not os.path.exists(os.path.join(a, "decision_table.csv")):
            pytest.skip(f"missing artefact {a}; run E5a windows first")
    return F.build_ml_dataset(ARTEFACTS, base_dir=".", grid_bounds=BOUNDS)


def test_no_outcome_leakage_in_features(dataset):
    for row in dataset["rows"]:
        overlap = set(row["features"]) & set(F.RETROSPECTIVE_OUTCOMES)
        assert not overlap, f"leakage in {row['keys']['decision_id']}: {overlap}"


def test_feature_schema_frozen(dataset):
    assert list(dataset["manifest"]["feature_schema"]) == list(
        F.DECISION_TIME_FEATURES)


def test_labels_match_frozen_definitions(dataset):
    for row in dataset["rows"]:
        mae, fwd = row["outcomes"]["mae"], row["outcomes"]["forward_return_3d"]
        assert row["outcomes"]["adverse_mae"] == (
            (mae < -0.01) if mae is not None else None)
        assert row["outcomes"]["adverse_forward_3d"] == (
            (fwd < -0.01) if fwd is not None else None)


def test_missingness_honest_not_imputed(dataset):
    assert dataset["manifest"]["feature_missingness"]["pre_trend_5d"] > 0
    for row in dataset["rows"]:
        assert "imputed" not in json.dumps(row)


def test_highvix_window_contributes_no_training_rows(dataset):
    assert "E5A-highvix-20260926" not in dataset["manifest"]["windows"]
    assert dataset["manifest"]["n_rows"] == 106
