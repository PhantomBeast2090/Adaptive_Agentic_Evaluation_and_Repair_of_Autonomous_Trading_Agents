"""Boundary scans: benchmarks stay inside the observation contract.

Canonical benchmarks must never reach past TargetObservation: no
environment or market access, no oracle shortcuts, no downstream
evaluation machinery (in particular nothing that encodes knowledge of
the repair provider), no clock/randomness, no adapt surface, no test
imports. Amendment-1 independence is enforced here as source text.
"""

import pathlib

_PACKAGE = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "benchmarks"
)


def _texts():
    return {
        path.name: path.read_text()
        for path in sorted(_PACKAGE.glob("*.py"))
    }


def _assert_absent(tokens):
    for name, text in _texts().items():
        for token in tokens:
            if token in text:
                raise AssertionError(f"{name} contains {token!r}")


def test_no_environment_or_market_access():
    _assert_absent(
        (
            "EnvironmentState",
            "InformationLookup",
            "IndianMultiAssetEnvironment",
            "read_csv",
            "read_parquet",
            "market_data",
            "env.step",
            "env.reset",
            "OraclePacket",
        )
    )


def test_no_downstream_evaluation_knowledge():
    # Amendment-1 independence: the benchmark must not encode knowledge
    # of repair-provider rules, guardrails, or test scaffolding.
    _assert_absent(
        (
            "per_session_order_cap",
            "hold_all",
            "rule-table",
            "TripleAgent",
            "ChurnAgent",
            "ExplodingAgent",
            "BrokenAgent",
            "GuardrailedAgent",
            "from tests",
            "import tests",
            "diagnostics.repair",
            "diagnostics.selection",
            "diagnostics.orchestration",
        )
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


def test_no_adapt_surface():
    _assert_absent((".adapt(", "adapt("))
