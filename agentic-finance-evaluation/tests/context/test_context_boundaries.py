"""E4-D boundary scans: E2-F paths stay memory-free; adapt is E4-only."""

import pathlib

_FROZEN = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "diagnostics"
    / "repair",
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "diagnostics"
    / "orchestration",
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "baseline",
)

_E4 = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "evaluation"
    / "context"
    / "assembly.py"
)


def _texts(directories):
    texts = {}
    for directory in directories:
        for path in sorted(directory.glob("*.py")):
            texts[f"{directory.name}/{path.name}"] = path.read_text()
    return texts


def _assert_absent(texts, tokens):
    for name, text in texts.items():
        for token in tokens:
            if token in text:
                raise AssertionError(f"{name} contains {token!r}")


def test_frozen_paths_know_no_e4_memory():
    _assert_absent(
        _texts(_FROZEN),
        (
            "LearnedContext",
            "MemoryStore",
            "evaluation.context.retrieval",
            "evaluation.context.assembly",
            "extract_candidate",
            "ContextPackage",
        ),
    )


def test_adapt_absent_from_frozen_eval_paths():
    _assert_absent(_texts(_FROZEN), (".adapt(",))


def test_adapt_present_only_in_e4_delivery():
    text = pathlib.Path(_E4).read_text()
    assert text.count(".adapt(") == 1


def test_benchmarks_have_no_repair_imports():
    # The contextual benchmark lives in evaluation/context (not the
    # frozen benchmarks/ package) precisely so frozen E3-C boundary
    # expectations stay untouched.
    bench = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "evaluation"
        / "context"
        / "benchmark.py"
    ).read_text()
    for token in (
        "evaluation.diagnostics.repair",
        "per_session_order_cap",
        "TripleAgent",
        "rule-table",
    ):
        assert token not in bench, f"contextual benchmark mentions {token!r}"
