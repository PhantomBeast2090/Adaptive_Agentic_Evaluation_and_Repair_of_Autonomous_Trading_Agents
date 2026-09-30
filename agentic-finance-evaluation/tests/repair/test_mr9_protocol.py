"""M-R9 protocol tests: frozen bank, isolation, leakage guards."""

import inspect
import importlib.util


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_mr9_for_test", "scripts/run_mr9.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_mr9 = _load_runner()


def _protocol():
    import yaml
    with open("configs/adaptive_repair/mr9_campaign.yaml") as handle:
        return yaml.safe_load(handle)


def test_bank_windows_match_plan_and_avoid_2020():
    protocol = _protocol()
    bank = protocol["window_bank"]
    assert sorted(bank) == ["R9-A", "R9-B", "R9-C", "R9-D", "R9-E", "R9-F"]
    spans = []
    for tag, triple in bank.items():
        for key in ("diagnostic", "heldout", "replication"):
            start, end = triple[key]["start"], triple[key]["end"]
            assert start < end
            assert "2020" not in start and "2020" not in end, (tag, key)
            spans.append((start, end, tag, key))
        assert triple["diagnostic"]["end"] < triple["heldout"]["start"]
        assert triple["heldout"]["end"] < triple["replication"]["start"]
    spans.sort()
    for (a0, a1, ka, ta), (b0, b1, kb, tb) in zip(spans, spans[1:]):
        assert a1 < b0, (ka + ta, kb + tb)


def test_detection_gates_match_mr6():
    import yaml
    protocol = _protocol()
    with open("configs/adaptive_repair/mr6_natural.yaml") as handle:
        mr6 = yaml.safe_load(handle)
    assert protocol["detection"] == mr6["detection"]
    for key in ("loss_chasing", "overtrading", "exposure", "volatility",
                "drawdown"):
        assert protocol["mechanism_templates"][key] == \
            mr6["mechanism_templates"][key]
    assert protocol["target"] == mr6["target"]
    assert protocol["normal_bound"] == mr6["normal_bound"]
    assert protocol["adjudication"] == mr6["adjudication"]
    assert protocol["agent"] == mr6["agent"]
    assert protocol["environment"] == mr6["environment"]


def test_runner_has_no_heldout_or_replication_before_freeze():
    source = inspect.getsource(run_mr9.run_experiment)
    head, _, _ = source.partition('write("freeze.json"')
    assert 'write("heldout.json"' not in head
    assert "served_held" not in head
    assert "base_held" not in head
    assert "repl-base" not in head
    assert "repl-rep" not in head
    assert 'write("replication.json"' not in head


def test_runner_never_reads_outcomes_for_selection():
    source = inspect.getsource(run_mr9.run_experiment).lower()
    head, _, _ = source.partition("mechanism_selected")
    for token in ("pnl", "profit", "sharpe"):
        assert token not in head, token


def test_episode_budget_enforced():
    protocol = _protocol()
    assert int(protocol["episode_budget"]["max_per_experiment"]) == 40
    assert int(protocol["episode_budget"]["max_campaign_total"]) == 240
    source = inspect.getsource(run_mr9.run_experiment)
    assert "episode budget" in source


def test_multiplicity_is_disclosure_only():
    protocol = _protocol()
    assert protocol["multiplicity"]["method"] == "disclosure-only"
    source = inspect.getsource(run_mr9).lower()
    assert "bonferroni" not in source
    assert "holm" not in source
    assert "fdr" not in source
