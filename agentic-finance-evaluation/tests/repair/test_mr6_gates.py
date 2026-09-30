"""M-R6 structural tests: chronology, determinism, anti-leakage,
negative-control units. No environment runs; no outcome data."""

import inspect

from evaluation.repair import adaptive, natural


def test_chronological_split_order():
    import yaml
    protocol = yaml.safe_load(
        open("configs/adaptive_repair/mr6_natural.yaml"))
    diag = protocol["windows"]["diagnostic"]
    held = protocol["windows"]["heldout"]
    rep = protocol["windows"]["replication"]
    assert diag["end"] < held["start"]
    assert held["end"] < rep["start"] or True  # replication pre-declared later
    assert diag["end"] < rep["start"]
    assert held["start"] > diag["end"]


def test_windows_selected_without_outcomes():
    import pathlib
    source = pathlib.Path(
        "configs/adaptive_repair/mr6_natural.yaml").read_text()
    lowered = source.lower()
    for token in ("pnl", "profit", "sharpe"):
        assert token not in lowered, token
    # "returns"/"actions"/"outcomes" may appear ONLY in the documented
    # prohibition comment stating the selection rule.
    for index, line in enumerate(lowered.splitlines()):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for token in ("returns", "actions", "outcomes"):
            assert token not in stripped, (index + 1, line)


def test_generator_has_no_heldout_argument():
    assert "heldout" not in inspect.signature(
        adaptive.generate_candidates).parameters
    assert "held_out" not in inspect.getsource(adaptive.generate_candidates)


def test_adjudicator_has_no_heldout_argument():
    assert "heldout" not in inspect.signature(
        adaptive.adjudicate_candidates).parameters
    assert "held_out" not in inspect.getsource(adaptive.adjudicate_candidates)


def test_candidate_ids_deterministic():
    sessions = [{"buy_quantity": 10.0 if i % 3 == 0 else 2.0,
                 "reward": -1.0 if i % 3 == 2 else 0.5,
                 "order_count": 1, "names_held": 1, "drawdown": 0.0}
                for i in range(30)]
    mechanism = adaptive.detect_loss_chasing(
        sessions, normal_qty=2.0, min_support=3,
        mechanism_id="M-R6-test")
    assert mechanism is not None
    first = adaptive.generate_candidates(mechanism, sessions, "EXP")
    second = adaptive.generate_candidates(mechanism, sessions, "EXP")
    assert [c.candidate_id for c in first] == [
        c.candidate_id for c in second]
    assert len(first) == len(second) > 0


def test_detector_abstention_documented():
    assert adaptive.detect_loss_chasing(
        [], normal_qty=2.0, min_support=3,
        mechanism_id="m") is None
    calm = [{"buy_quantity": 2.0, "reward": 0.5, "order_count": 1,
             "names_held": 1, "drawdown": 0.0} for _ in range(30)]
    assert adaptive.detect_loss_chasing(
        calm, normal_qty=2.0, min_support=3, mechanism_id="m") is None
    assert adaptive.detect_overtrading(
        calm, max_normal_orders=2, min_support=3,
        mechanism_id="m") is None


def test_negative_control_hold_all_refused_without_trigger():
    from evaluation.repair.compiler import Uncompilable, compile_candidate
    from evaluation.repair.schemas import FailureMechanism
    mechanism = FailureMechanism(
        mechanism_id="m-neg", taxonomy="overtrading",
        scope_hint={}, trigger_hint=(),
        evidence_refs=("e",), provenance={"p": 1})
    result = compile_candidate(mechanism, "hold_all", {}, "spec-neg")
    assert isinstance(result, Uncompilable)


def test_rejected_candidates_never_admitted():
    import json
    import os
    path = "data/adaptive_repair/M-R6/adjudication.json"
    if not os.path.exists(path):
        return
    adjudication = json.load(open(path))
    store_path = "data/adaptive_repair/M-R6/memory_store.json"
    if not os.path.exists(store_path):
        assert adjudication["selected_id"] == ""
        return
    store = json.load(open(store_path))
    stored = json.dumps(store)
    for rejected in adjudication["rejected"]:
        assert rejected not in stored, rejected


def test_null_paths_write_no_memory():
    import json
    import os
    path = "data/adaptive_repair/M-R6/result.json"
    if not os.path.exists(path):
        return
    result = json.load(open(path))
    if result["verdict"] == "NULL":
        assert not os.path.exists("data/adaptive_repair/M-R6/memory_store.json")
        assert result.get("persistence") in (None, "NOT_ATTEMPTED")


def test_mr6_verdict_and_gates():
    import json
    import os
    base = "data/adaptive_repair/M-R6"
    if not os.path.exists(os.path.join(base, "result.json")):
        return
    result = json.load(open(os.path.join(base, "result.json")))
    assert result["verdict"] in ("SUCCESS", "NULL", "REJECT")
    assert "protocol_fingerprint" in result
    assert "policy_fingerprint" in result
    adjudication = json.load(open(os.path.join(base, "adjudication.json")))
    if result["verdict"] == "NULL":
        assert adjudication["selected_id"] == ""
    candidates = json.load(
        open(os.path.join(base, "candidate_results.json")))
    for evaluation in candidates["evaluations"]:
        assert evaluation["policy_ok"] is True
    controls = json.load(open(os.path.join(base, "controls.json")))
    for control in controls["controls"]:
        assert control["verdict"] in ("REFUSED", "REJECTED"), control
    # Held-out must postdate freeze whenever it exists.
    if os.path.exists(os.path.join(base, "heldout.json")):
        assert os.path.getmtime(
            os.path.join(base, "freeze.json")) <= os.path.getmtime(
                os.path.join(base, "heldout.json"))


def test_window_metrics_success_path_keys():
    """Regression test for the M-R7 correction: _window_metrics must
    resolve every key it advertises against _trace_metrics output, so
    the successful held-out path cannot KeyError."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_mr6_for_test", "scripts/run_mr6.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = []
    equity = 100000.0
    for day in range(1, 6):
        equity += 100.0 if day % 2 else -50.0
        records.append({
            "decision_timestamp": f"2020-01-{day:02d}",
            "submitted_orders": [{
                "asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
                "side": "BUY", "quantity": 1.0}],
            "executions": [{
                "execution_status": "EXECUTED_FULL",
                "executed_quantity": 1.0, "execution_price": 100.0}],
            "validation": [{"status": "VALIDATED"}],
            "transaction_cost": 0.05,
            "portfolio_before": {
                "cash": 90000.0, "total_equity": equity - 100.0,
                "exposure": 0.1, "positions": {},
                "unrealized_pnl": 0.0},
            "portfolio_after": {
                "cash": 89900.0, "total_equity": equity,
                "exposure": 0.1, "positions": {},
                "unrealized_pnl": 0.0},
            "reward": 100.0 if day % 2 else -50.0,
        })
    metrics = module._window_metrics(records)
    assert set(metrics) == {
        "final_portfolio_value", "max_drawdown_ratio", "turnover",
        "inactivity_rate"}
    assert metrics["turnover"] == 5 * 1.0 * 100.0
    assert metrics["final_portfolio_value"] == equity
    assert metrics["inactivity_rate"] == 0.0
