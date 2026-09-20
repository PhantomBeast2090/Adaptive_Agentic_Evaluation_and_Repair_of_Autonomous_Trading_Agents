"""Harness boundary scans and signature-level isolation proofs.

- No Tier-2 statistical machinery anywhere in experiments/harness.
- No wall-clock/randomness tokens in harness identity paths.
- Frozen substrate never imports the harness (dependency direction).
- SealedBaseline has no parameter in diagnosis/repair/validation/
  stopping/select functions (signature inspection, not comments).
"""

import inspect
import pathlib

PACKAGE = (
    pathlib.Path(__file__).resolve().parent.parent.parent.parent
    / "experiments"
    / "harness"
)
REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


def _texts():
    return {
        path.name: path.read_text()
        for path in sorted(PACKAGE.glob("*.py"))
    }


def _assert_absent(tokens):
    for name, text in _texts().items():
        for token in tokens:
            if token in text:
                raise AssertionError(f"{name} contains {token!r}")


def test_no_tier2_statistical_machinery():
    _assert_absent(
        (
            "scipy",
            "statsmodels",
            "sklearn",
            "mannwhitneyu",
            "p_value",
            "p-value",
            "confidence_interval",
            "hodges",
            "wilcoxon",
            "ttest",
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
            "hostname",
        )
    )


def test_frozen_substrate_does_not_import_harness():
    roots = (
        REPO / "evaluation",
        REPO / "environment",
        REPO / "benchmarks",
    )
    offenders = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "experiments.harness" in path.read_text():
                offenders.append(str(path))
    assert offenders == []


def _signature_names(function):
    return list(inspect.signature(function).parameters)


def test_sealed_baseline_absent_from_sensitive_signatures():
    from experiments.harness import lifecycle

    for name in ("diagnose", "phase_b", "phase_c"):
        params = _signature_names(getattr(lifecycle, name))
        assert "sealed_nh" not in params, name
        assert "sealed" not in " ".join(params), name


def test_frozen_selector_and_repair_take_no_sealed_input():
    from evaluation.diagnostics.repair.results import run_repair
    from evaluation.diagnostics.selection.selector import select_next_test

    for function in (select_next_test, run_repair):
        source = inspect.getsource(function)
        assert "SealedBaseline" not in source
        assert "sealed_nh" not in source


def test_single_shared_diagnostic_call_site():
    text = (PACKAGE / "lifecycle.py").read_text()
    assert text.count("execute(") == 1
    assert "def diagnose(" in text
