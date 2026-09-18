"""Source-boundary scans: no env/market/exec/repair/learn/Bayes/clock/ranking."""

import pathlib

_PACKAGE = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "diagnostics"
    / "selection"
)


def _texts():
    return {
        path.name: path.read_text() for path in sorted(_PACKAGE.glob("*.py"))
    }


def _assert_absent(tokens, *, allow_negation=False):
    import re

    negation = re.compile(r"\b(no|without|never|not|non-|against|why)\b", re.I)
    for name, text in _texts().items():
        for token in tokens:
            if token not in text:
                continue
            if allow_negation:
                offending = [
                    line.strip()
                    for line in text.splitlines()
                    if token in line and not negation.search(line)
                ]
                assert not offending, f"{name} affirms {token!r}: {offending}"
            else:
                raise AssertionError(f"{name} contains {token!r}")


def test_no_environment_or_market_access():
    _assert_absent(
        (
            "IndianMultiAssetEnvironment",
            "EnvironmentState",
            "InformationLookup",
            "market_data",
            "read_csv",
            "read_parquet",
            "env.step",
            "env.reset",
        )
    )


def test_no_execution_repair_or_learning():
    _assert_absent(
        (
            "executor",
            "execute(",
            "retrain",
            "gradient",
            ".fit(",
            "repair",
            "learn",
        )
    )


def test_no_bayesian_or_information_gain_machinery():
    _assert_absent(
        ("bayes", "posterior", "likelihood", "entropy", "KL divergence"),
        allow_negation=True,
    )


def test_no_randomness_or_wall_clock_identity():
    _assert_absent(
        (
            "random.",
            "uuid",
            "datetime.now",
            "time.time",
            "perf_counter",
            "os.getpid",
            "secrets.",
        )
    )


def test_no_ranking_or_optimality_claims():
    _assert_absent(
        (
            "optimal",
            "best test",
            "best_test",
            "most informative",
            "information gain",
            "winning hypothesis",
            "winning_hypothesis",
            "most likely",
            "posterior",
            "top hypothesis",
            "argmax",
            "argsort",
            "rank_hyp",
            "select_best",
        ),
        allow_negation=True,
    )


def test_no_new_metrics():
    _assert_absent(
        (
            "MetricResult",
            "Sharpe",
            "sharpe",
            "drawdown",
            "VaR",
            "CVaR",
            "volatility",
        )
    )


def test_selection_computes_no_scores():
    from evaluation.diagnostics.selection import select_next_test

    from .fixtures import make_rival_state

    out = select_next_test(make_rival_state())
    assert "selection_score" not in out.to_dict()
    import evaluation.diagnostics.selection.selector as _selector

    assert "selection_score=None" in pathlib.Path(_selector.__file__).read_text()


def test_no_hypothesis_fields_in_selection_key():
    from evaluation.diagnostics.selection.candidates import candidate_statistics

    from .fixtures import make_rival_state

    fresh = make_rival_state()
    test = next(t for t in fresh.available_tests if t.test_id == "T-1")
    stats = candidate_statistics(fresh, test)
    assert stats.selection_key() == (-1, -2, 2.0, "T-1")
