"""Boundary scans: no env/market/oracle/repair/learn/Bayes/clock/randomness."""

import pathlib

from ..execution_fixtures import (
    baseline_spec as real_spec,  # noqa: F401
)

_PACKAGE = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "diagnostics"
    / "orchestration"
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


def test_no_oracle_or_observation_reconstruction():
    _assert_absent(("OraclePacket", "TargetObservation"))


def test_no_repair_or_learning_apis():
    _assert_absent(
        (
            "adapt(",
            "repair",
            "Retrain",
            "retrain",
            "gradient",
            ".fit(",
            "learn",
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


def test_no_hypothesis_ranking_or_optimality():
    _assert_absent(
        (
            "argmax",
            "argsort",
            "best_hypothesis",
            "winner",
            "rank_hyp",
            "select_best",
            "top hypothesis",
        ),
        allow_negation=True,
    )


def test_controller_never_calls_adapt(real_spec):
    from ..execution_fixtures import HoldAgent
    from .fixtures import (
        make_loop_baseline,
        make_loop_config,
        make_loop_state,
    )
    from ..execution_fixtures import make_null_test
    from ..selection.fixtures import add_prediction
    from evaluation.diagnostics.orchestration.controller import run

    class SpyAgent(HoldAgent):
        identity = HoldAgent.identity

        def __init__(self):
            self.adapt_calls = []

        def adapt(self, *args, **kwargs):
            self.adapt_calls.append((args, kwargs))

    baseline = make_loop_baseline()
    agent = SpyAgent()
    state = make_loop_state(
        baseline, real_spec, diagnostic_id="D-SPY", agent=agent
    )
    state.register_test(make_null_test(test_id="T-1"))
    add_prediction(state, "P-1", "H-1", "T-1", "INCREASE")
    config = make_loop_config(
        baseline, agent, max_iterations=1, diagnostic_id="D-SPY"
    )
    run(
        diagnostic_state=state, baseline=baseline,
        target_agent=agent, config=config,
    )
    assert agent.adapt_calls == []
