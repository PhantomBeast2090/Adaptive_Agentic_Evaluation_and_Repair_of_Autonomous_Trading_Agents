"""Foundation-layer tests: PIT, determinism, metadata, graceful-skip.

All tests run without foundation-model weights: a deterministic stub
stands in for live models, and live-model tests assert probe shapes
and status taxonomy only.
"""

import csv
import os

import pytest

from evaluation.ml.diagnosis.forecast_diagnostics import (
    EVALUATOR_ONLY, MODEL_DERIVED, OBSERVED,
)
from evaluation.ml.forecasting import forecast_features as FF
from evaluation.ml.forecasting.base import (
    ForecastOutput, context_fingerprint,
)
from evaluation.ml.forecasting.feature_adapter import build_context
from evaluation.ml.models import registry as REG
from evaluation.ml.models.hist_gradient_boosting import HGBModel
from evaluation.ml.models.timeseries_base import ModelStatus


@pytest.fixture()
def tiny_equity(tmp_path):
    base = str(tmp_path)
    rel = "data/processed/india/equities/nse_equity_daily.csv"
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="") as h:
        w = csv.writer(h)
        w.writerow(["observation_date", "symbol", "close", "high", "low",
                    "traded_quantity"])
        for i in range(10):
            w.writerow([f"2023-05-{10 + i:02d}", "RELIANCE",
                        f"{100 + i}", f"{101 + i}", f"{99 + i}", "1000"])
    return base


def test_pit_context_excludes_future_and_fingerprint_stable(tiny_equity):
    c1 = build_context("RELIANCE:EQ", "2023-05-15", base_dir=tiny_equity)
    assert c1["stamps"]["close"][-1] == "2023-05-14"
    assert all(s < "2023-05-15" for s in c1["stamps"]["close"]
               ), "T+1 or later bar present in context"
    # mutate the future: input fingerprint must not move
    p = os.path.join(
        tiny_equity, "data/processed/india/equities/nse_equity_daily.csv")
    with open(p, "a") as h:
        h.write("2023-05-16,RELIANCE,9999,9999,9999,5\n")
    from evaluation.attribution import features_v2 as F2
    F2._CACHE.clear()
    c2 = build_context("RELIANCE:EQ", "2023-05-15", base_dir=tiny_equity)
    assert c1["context_fingerprint"] == c2["context_fingerprint"]
    assert c2["reference_level"] == c1["reference_level"]


def test_insufficient_history_preserved_as_missing(tiny_equity):
    with pytest.raises(ValueError):
        build_context("RELIANCE:EQ", "2023-05-10", base_dir=tiny_equity)


class StubTS:
    """Deterministic stand-in TimeSeriesModel (no weights)."""

    def forecast(self, context):
        ref = context["reference_level"]
        paths = (tuple([ref * 0.99] * 5),
                 tuple([ref] * 5),
                 tuple([ref * 1.01] * 5))
        return ForecastOutput(
            model_id="stub", model_version="0", checkpoint_revision="none",
            decision_id=context.get("decision_id", ""),
            instrument=context.get("instrument", ""),
            decision_timestamp=context.get("decision_timestamp", ""),
            context_fingerprint=context["context_fingerprint"],
            horizons=(1, 3, 5), quantiles=(0.1, 0.5, 0.9),
            quantile_paths=paths, reference_level=ref,
            deterministic_seed=1, status=ModelStatus.AVAILABLE)


def test_forecast_determinism_and_roundtrip(tiny_equity):
    ctx = build_context("RELIANCE:EQ", "2023-05-15", base_dir=tiny_equity)
    ctx = dict(ctx, decision_id="d", instrument="RELIANCE:EQ",
               decision_timestamp="2023-05-15")
    stub = StubTS()
    a = stub.forecast(ctx)
    b = stub.forecast(ctx)
    assert a.output_fingerprint() == b.output_fingerprint()
    assert ForecastOutput.from_dict(a.to_dict()) == a
    bad = a.to_dict()
    bad["predicted_price"] = 1.0
    with pytest.raises(ValueError):
        ForecastOutput.from_dict(bad)


def test_forecast_features_fixed_schema_and_honest_nones():
    blocked = ForecastOutput(
        model_id="x", model_version="0", checkpoint_revision="none",
        decision_id="d", instrument="i", decision_timestamp="t",
        context_fingerprint="c", horizons=(1, 3, 5),
        quantiles=(0.1, 0.5, 0.9),
        quantile_paths=tuple(tuple([None] * 5) for _ in range(3)),
        reference_level=None, deterministic_seed=None,
        status=ModelStatus.UNAVAILABLE, failure_reason="probe")
    row = FF.derive(blocked)
    assert set(row) == set(FF.FORECAST_DERIVED_FEATURES)
    assert all(v is None for v in row.values())


def test_optionals_lazy_no_heavy_imports():
    import sys
    for mod in ("chronos", "chronos2", "timesfm", "timesfm3", "torch"):
        assert mod not in sys.modules or mod == "torch", (
            f"{mod} eagerly imported by evaluation.ml")


def test_registry_status_taxonomy():
    rows = REG.describe()
    assert {r["model_id"] for r in rows} == {
        "logistic", "hgb", "tabpfn", "chronos2", "timesfm3"}
    valid = {ModelStatus.AVAILABLE, ModelStatus.BLOCKED_MISSING_DEPENDENCY,
             ModelStatus.BLOCKED_MISSING_WEIGHTS,
             ModelStatus.BLOCKED_AUTHORIZATION, ModelStatus.BLOCKED_LICENSE,
             ModelStatus.RESOURCE_LIMIT, ModelStatus.UNAVAILABLE}
    assert all(r["status"] in valid for r in rows)
    with pytest.raises(Exception):
        REG.make_tabular("no-such-model", [])


def test_hgb_deterministic_and_metadata():
    X = [[float(i), float(i % 2)] for i in range(12)]
    y = [i % 2 for i in range(12)]
    m1 = HGBModel(["a", "b"]).fit(X, y)
    m2 = HGBModel(["a", "b"]).fit(X, y)
    assert m1.predict_proba(X) == m2.predict_proba(X)
    meta = m1.metadata()
    assert meta["random_seed"] == 20260926
    assert "library_version" in meta and meta["device"] == "cpu"


def test_license_metadata_constants():
    from evaluation.ml.models import chronos2 as C2
    from evaluation.ml.models import timesfm3 as T3
    assert C2.CHRONOS_LICENSE == "Apache-2.0"
    assert T3.TIMESFM_LICENSE == "timesfm-non-commercial-license-v1.0"
    assert "Non-Commercial" in T3.TIMESFM_CITATION
    assert C2.CHRONOS_PRIMARY == "amazon/chronos-2"
    assert C2.CHRONOS_FALLBACK == "autogluon/chronos-2-small"


def test_chronos_fallback_defaults_to_primary_unloaded():
    from evaluation.ml.models import chronos2 as C2
    m = C2.Chronos2Model()
    assert m.checkpoint == C2.CHRONOS_PRIMARY
    assert m.metadata()["fallback_used"] is False


def test_provenance_tags_exist():
    assert (OBSERVED, MODEL_DERIVED, EVALUATOR_ONLY) == (
        "OBSERVED", "MODEL_DERIVED", "EVALUATOR_ONLY")
