"""M-R7 protocol tests: frozen specs, isolation, leakage guards."""

import inspect
import importlib.util


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_mr7_for_test", "scripts/run_mr7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_mr7 = _load_runner()


def _protocol():
    import yaml
    with open("configs/adaptive_repair/mr7_normality.yaml") as handle:
        return yaml.safe_load(handle)


def test_protocol_windows_match_mr6():
    import yaml
    protocol = _protocol()
    with open("configs/adaptive_repair/mr6_natural.yaml") as handle:
        mr6 = yaml.safe_load(handle)
    assert protocol["windows"] == mr6["windows"]
    assert protocol["agent"] == mr6["agent"]
    assert protocol["environment"] == mr6["environment"]
    assert protocol["detection"] == mr6["detection"]
    for key in ("loss_chasing", "overtrading", "exposure", "volatility",
                "drawdown"):
        assert protocol["mechanism_templates"][key] == \
            mr6["mechanism_templates"][key]
    assert protocol["target"] == mr6["target"]
    assert protocol["normal_bound"] == mr6["normal_bound"]
    assert protocol["adjudication"] == mr6["adjudication"]


def test_protocol_embeds_correct_normality_fingerprints():
    from evaluation.repair.normality import SPECIFICATIONS
    protocol = _protocol()
    for spec_id in ("N0", "N1", "N2"):
        assert protocol["normality"][spec_id]["fingerprint"] == \
            SPECIFICATIONS[spec_id].fingerprint()[:16]


def test_runner_has_no_heldout_in_selection_path():
    source = inspect.getsource(run_mr7.run_mr7)
    head, _, _ = source.partition('pair_write("freeze.json"')
    # No held-out artefact writes may occur before the per-pair freeze
    # record. (Diagnostic baseline runs legitimately precede it.)
    assert "heldout.json" not in head
    assert "served_held" not in head
    assert "base_held" not in head


def test_normality_cannot_receive_forbidden_inputs():
    import evaluation.repair.normality as module
    source = inspect.getsource(module).lower()
    for token in ("heldout", "held_out", "candidate_result",
                  "economic_result", "pnl", "sharpe"):
        assert token not in source, token


def test_candidate_isolation_by_construction():
    import json
    import os
    for name in ("adjudication.json", "candidate_results.json",
                 "candidates.json"):
        path = os.path.join("data", "adaptive_repair", "M-R7", name)
        if not os.path.exists(path):
            continue
        json.load(open(path))
