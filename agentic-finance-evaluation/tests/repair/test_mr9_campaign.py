"""M-R9 campaign unit tests: activity flags, status map, readings."""

from evaluation.repair import activity as A
from evaluation.repair.activity import annotate_mechanism_active


def _sessions():
    return [
        {"session": f"s{i}", "buy_quantity": q, "sell_quantity": 0.0,
         "order_count": oc, "names_held": nh, "reward": rw,
         "drawdown": dd, "vix": vx}
        for i, (q, oc, nh, rw, dd, vx) in enumerate([
            (2.0, 1, 1, 0.5, 0.0, 12.0),
            (4.0, 1, 1, -1.0, 0.0, 12.0),
            (6.0, 3, 3, 0.5, 0.06, 30.0),
            (1.0, 1, 4, 0.5, 0.0, 12.0),
        ])
    ]


def test_exposure_flags_match_frozen_bound():
    rows = annotate_mechanism_active(
        _sessions(), "exposure", {"max_normal_names": 2})
    assert [r["exposure_active"] for r in rows] == [
        False, False, True, True]


def test_overtrading_flags_match_frozen_bound():
    rows = annotate_mechanism_active(
        _sessions(), "overtrading", {"max_normal_orders": 2})
    assert [r["overtrading_active"] for r in rows] == [
        False, False, True, False]


def test_loss_chasing_requires_prior_loss():
    rows = annotate_mechanism_active(
        _sessions(), "loss_chasing", {"normal_qty": 2.0})
    # s0 no prev; s1 prev s0 non-negative; s2 prev s1 negative + qty 6;
    # s3 prev s2 non-negative.
    assert [r["loss_chasing_active"] for r in rows] == [
        False, False, True, False]


def test_volatility_flags_match_frozen_bound():
    rows = annotate_mechanism_active(
        _sessions(), "volatility", {"vix_high": 25.0})
    assert [r["volatility_active"] for r in rows] == [
        False, False, True, False]


def test_drawdown_flags_match_frozen_bound():
    rows = annotate_mechanism_active(
        _sessions(), "drawdown",
        {"drawdown_threshold": 0.05, "normal_qty": 2.0})
    assert [r["drawdown_active"] for r in rows] == [
        False, False, True, False]


def test_missing_fields_fail_closed():
    for mech, bounds in [
            ("exposure", {"max_normal_names": 2}),
            ("overtrading", {"max_normal_orders": 2}),
            ("loss_chasing", {"normal_qty": 2.0}),
            ("volatility", {"vix_high": 25.0}),
            ("drawdown", {"drawdown_threshold": 0.05,
                          "normal_qty": 2.0})]:
        rows = annotate_mechanism_active([{}], mech, bounds)
        assert rows[0][f"{mech}_active"] is False
        assert A.activity_flag({}, mech) is False


def test_unknown_mechanism_raises():
    try:
        annotate_mechanism_active(_sessions(), "momentum", {})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown mechanism must raise")


def test_status_precedence():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_mr9_status", "scripts/run_mr9.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._status_for(
        {"shadow_failed": True, "reject_reasons": []}, False) == \
        "SHADOW_FAILED"
    assert module._status_for(
        {"shadow_failed": False,
         "reject_reasons": ["policy fingerprint changed"]},
        False) == "POLICY_CHANGED"
    assert module._status_for(
        {"shadow_failed": False, "reject_reasons": ["validity regression"]},
        False) == "SAFETY_REJECT"
    assert module._status_for(
        {"shadow_failed": False, "reject_reasons": ["full inactivity"]},
        False) == "INACTIVITY_REJECT"
    assert module._status_for(
        {"shadow_failed": False,
         "reject_reasons": ["economic regression beyond tolerance"]},
        False) == "ECONOMIC_GATE_REJECT"
    assert module._status_for(
        {"shadow_failed": False,
         "reject_reasons": ["bootstrap CI does not exclude null"]},
        False) == "STATISTICAL_NULL"
    assert module._status_for(
        {"shadow_failed": False,
         "reject_reasons": ["normal-session behaviour altered"]},
        False) == "SPECIFICITY_REJECT"
    assert module._status_for(
        {"shadow_failed": False, "reject_reasons": []}, False) == \
        "ADMISSIBLE"


def test_activity_module_has_no_forbidden_channels():
    import inspect
    import evaluation.repair.activity as module
    source = inspect.getsource(module).lower()
    for token in ("heldout", "held_out", "candidate_result",
                  "economic_result", "pnl", "sharpe", "profit"):
        assert token not in source, token
