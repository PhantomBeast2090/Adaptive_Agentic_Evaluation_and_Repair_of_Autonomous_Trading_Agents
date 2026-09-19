"""Boundary scans: no env/market/oracle/repair-learn/Bayes/clock/randomness."""

import pathlib

_PACKAGE = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "diagnostics"
    / "repair"
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
            "read_csv",
            "read_parquet",
            "market_data",
            "env.step",
            "env.reset",
        )
    )


def test_no_oracle_or_observation_shortcuts():
    _assert_absent(("OraclePacket",))


def test_no_repair_learning_or_optimisation():
    _assert_absent(
        (
            "retrain",
            "gradient",
            ".fit(",
            "reinforce",
            "meta-learn",
            "metalearn",
            "policy optimisation",
            "policy optimization",
        )
    )


def test_no_bayesian_machinery():
    _assert_absent(
        ("bayes", "posterior", "likelihood", "prior probability"),
        allow_negation=True,
    )


def test_no_wall_clock_or_randomness():
    _assert_absent(
        (
            "datetime.now",
            "time.time",
            "perf_counter",
            "uuid",
            "random.",
            "os.getpid",
            "secrets.",
        )
    )


def test_no_adapt_calls_in_repair_paths():
    _assert_absent((".adapt(", "adapt("))
