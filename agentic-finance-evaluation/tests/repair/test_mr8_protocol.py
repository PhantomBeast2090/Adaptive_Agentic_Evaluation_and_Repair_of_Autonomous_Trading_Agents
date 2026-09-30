"""M-R8 protocol tests: strict isolation, frozen trigger, N1 fixed."""

import inspect
import importlib.util


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_mr8_for_test", "scripts/run_mr8.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_mr8 = _load_runner()


def _protocol():
    import yaml
    with open("configs/adaptive_repair/mr8_conditional.yaml") as handle:
        return yaml.safe_load(handle)


def test_protocol_windows_agent_env_match_mr6():
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


def test_conditional_block_is_frozen_exposure_only():
    protocol = _protocol()
    cond = protocol["conditional"]
    assert cond["mechanism"] == "exposure"
    assert cond["field"] == "names_held"
    assert cond["operator"] == "gt"
    assert int(cond["threshold"]) == 2
    assert set(cond) <= {"mechanism", "field", "operator", "threshold",
                         "method", "version"}


def test_adjudication_normality_fixed_n1():
    protocol = _protocol()
    assert protocol["normality"]["adjudication"] == "N1"
    assert int(protocol["normality"]["exposure_normal_names"]) == 2
    from evaluation.repair.normality import SPECIFICATIONS
    for spec_id in ("N0", "N1", "N2"):
        assert protocol["normality"][spec_id]["fingerprint"] == \
            SPECIFICATIONS[spec_id].fingerprint()[:16]


def test_runner_has_no_heldout_or_replication_before_freeze():
    source = inspect.getsource(run_mr8.run_mr8)
    head, _, _ = source.partition('write("freeze.json"')
    # No held-out artefact WRITES, held-out RUNS, or replication RUNS may
    # occur before the freeze record. (Reading the pre-registered window
    # config and guarding heldout.json absence pre-freeze is legitimate.)
    assert 'write("heldout.json"' not in head
    assert "served_held" not in head
    assert "base_held" not in head
    assert "repl-base" not in head
    assert "repl-rep" not in head
    assert 'write("replication.json"' not in head


def test_conditional_module_has_no_forbidden_channels():
    import evaluation.repair.conditional as module
    source = inspect.getsource(module).lower()
    for token in ("heldout", "held_out", "candidate_result",
                  "economic_result", "pnl", "sharpe"):
        assert token not in source, token
    params = list(inspect.signature(
        module.exposure_active_from_payload).parameters)
    assert params == ["payload"]


def test_chronological_split_order():
    protocol = _protocol()
    diag = protocol["windows"]["diagnostic"]
    held = protocol["windows"]["heldout"]
    rep = protocol["windows"]["replication"]
    assert diag["end"] < held["start"]
    # Replication predates held-out by design; require disjointness.
    assert rep["end"] < held["start"] or rep["start"] > held["end"]
    assert diag["end"] < rep["start"]
    assert held["start"] > diag["end"]
