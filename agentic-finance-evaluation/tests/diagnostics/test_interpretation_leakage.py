"""Boundary scans: no env/market/rerun, no Bayes, no clock, no ranking (points 23-30, 39)."""

import pytest

from evaluation.diagnostics.interpretation.summary import InterpretationRecord

from .interpretation_fixtures import make_baseline


def _package_texts():
    import pathlib

    package = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "evaluation"
        / "diagnostics"
        / "interpretation"
    )
    return {path.name: path.read_text() for path in sorted(package.glob("*.py"))}


def test_no_raw_environment_access():
    texts = _package_texts()
    forbidden = (
        "IndianMultiAssetEnvironment",
        "EnvironmentState",
        "InformationLookup",
        "read_csv",
        "read_parquet",
        "env.step",
        "env.reset",
        "market_data",
    )
    for name, text in texts.items():
        for token in forbidden:
            assert token not in text, f"{name} contains {token!r}"


def test_no_bayesian_or_probabilistic_machinery():
    import re

    texts = _package_texts()
    # Negating disclaimers ("no Bayesian machinery") are required prose;
    # only affirmative machinery claims are forbidden.
    allowed = re.compile(r"\b(no|without|never|not|non-|against|ban)\b", re.I)
    for name, text in texts.items():
        lowered = text.lower()
        for token in ("bayes", "posterior", "likelihood", "prior probability"):
            if token not in lowered:
                continue
            offending = [
                line.strip()
                for line in text.splitlines()
                if token in line.lower() and not allowed.search(line)
            ]
            assert not offending, f"{name} affirms {token!r}: {offending}"


def test_no_wall_clock_random_or_uuid_identity():
    texts = _package_texts()
    for name, text in texts.items():
        for token in (
            "datetime.now",
            "time.time",
            "perf_counter",
            "uuid",
            "random.",
            "os.getpid",
            "secrets.",
        ):
            assert token not in text, f"{name} contains {token!r}"


def test_no_ranking_selection_repair_or_learning():
    texts = _package_texts()
    for name, text in texts.items():
        lowered = text.lower()
        for token in (
            "argmax",
            "argsort",
            "best_hypothesis",
            "winner",
            "rank_hyp",
            "select_best",
            "top_k",
            "retrain",
            "gradient",
        ):
            assert token not in lowered, f"{name} contains {token!r}"
    # "repair"/"selection" may appear in prose disclaimers only; the
    # modules must not implement them — assert no such callables exist.
    import evaluation.diagnostics.interpretation.interpreter as _interp
    import evaluation.diagnostics.interpretation.updates as _updates

    for module in (_interp, _updates):
        names = {name.lower() for name in dir(module)}
        assert not any("repair" in n or "learn" in n for n in names)


def test_repeated_interpretation_is_identical():
    from .interpretation_fixtures import make_interpret_state
    from .interpretation_fixtures import make_diagnostic_result
    from evaluation.diagnostics.interpretation.interpreter import interpret

    def _run_once():
        baseline = make_baseline({"turnover": 1.0})
        state, _ = make_interpret_state(baseline)
        result = make_diagnostic_result(baseline, {"turnover": 0.8})
        state.record_result(result)
        record = interpret(
            diagnostic_state=state,
            result_id="R-1",
            prediction_ids=["P-1"],
            baseline=baseline,
        )
        return record, state

    first_record, first_state = _run_once()
    second_record, second_state = _run_once()
    assert first_record.fingerprint() == second_record.fingerprint()
    assert first_record.to_dict() == second_record.to_dict()
    assert (
        first_state.hypothesis_updates[0].fingerprint()
        == second_state.hypothesis_updates[0].fingerprint()
    )
    assert first_state.uncertainty.to_dict() == second_state.uncertainty.to_dict()


def test_summary_round_trip_and_fingerprint():
    from .interpretation_fixtures import (
        make_diagnostic_result,
        make_interpret_state,
    )
    from evaluation.diagnostics.interpretation.interpreter import interpret

    baseline = make_baseline({"turnover": 1.0})
    state, _ = make_interpret_state(baseline)
    result = make_diagnostic_result(baseline, {"turnover": 0.8})
    state.record_result(result)
    record = interpret(
        diagnostic_state=state,
        result_id="R-1",
        prediction_ids=["P-1"],
        baseline=baseline,
    )
    restored = InterpretationRecord.from_dict(record.to_dict())
    assert restored == record
    assert restored.fingerprint() == record.fingerprint()
    assert record.uncertainty_id == "D-1:ua:R-1"
    assert record.update_ids == tuple(
        u.update_id for u in state.hypothesis_updates
    )
    with pytest.raises(ValueError):
        InterpretationRecord.from_dict(
            {**record.to_dict(), "unknown_field": 1}
        )
