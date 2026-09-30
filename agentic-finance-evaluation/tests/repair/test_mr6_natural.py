"""M-R6 adapter tests: field derivation, forbidden legs, edge cases."""

from evaluation.repair import natural


def _record(**over):
    base = {
        "decision_timestamp": "2020-03-12",
        "state_fingerprint": "abc",
        "visible_assets": ("nse_equity:RELIANCE:EQ", "indiavix"),
        "unavailable_assets": (),
        "submitted_orders": (
            {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
             "side": "BUY", "quantity": 2.0},
            {"asset_id": "nse_equity", "instrument": "TCS:EQ",
             "side": "SELL", "quantity": 1.0},
        ),
        "validation": (),
        "executions": (),
        "transaction_cost": 0.5,
        "portfolio_before": {
            "cash": 90000.0, "total_equity": 100000.0, "exposure": 0.1,
            "holdings_value": 10000.0,
            "positions": {"nse_equity:TCS:EQ": {"quantity": 1.0}},
            "realized_pnl": 0.0, "unrealized_pnl": -2000.0,
            "cumulative_costs": 0.0,
        },
        "portfolio_after": {},
        "reward": -5.0,
        "environment_metadata": {},
    }
    base.update(over)
    return base


def test_field_derivation_documented():
    rows = natural.adapt_records([_record()], {"2020-03-11": 20.0})
    assert len(rows) == 1
    row = rows[0]
    assert row["session"] == "2020-03-12"
    assert row["buy_quantity"] == 2.0
    assert row["sell_quantity"] == 1.0
    assert row["order_count"] == 2
    assert row["names_held"] == 1
    assert row["exposure"] == 0.1
    assert row["reward"] == -5.0
    assert row["vix"] == 20.0  # as-of join, prior close
    assert row["unrealized_drawdown"] == 0.02
    assert row["drawdown"] == 0.0  # first observation defines the peak


def test_drawdown_tracks_peak_without_future():
    rows = natural.adapt_records([
        _record(decision_timestamp="2020-03-12"),
        _record(decision_timestamp="2020-03-13"),
    ], {})
    assert rows[0]["drawdown"] == 0.0
    rec = _record(decision_timestamp="2020-03-13")
    rec["portfolio_before"] = dict(rec["portfolio_before"])
    rec["portfolio_before"]["total_equity"] = 90000.0
    rows = natural.adapt_records([
        _record(decision_timestamp="2020-03-12"), rec], {})
    assert abs(rows[1]["drawdown"] - 0.1) < 1e-9


def test_forbidden_retrospective_legs_rejected():
    bad = _record()
    bad["mae"] = -0.02
    try:
        natural.adapt_records([bad], {})
    except ValueError:
        pass
    else:
        raise AssertionError("MAE leg must be refused")
    bad2 = _record()
    bad2["forward_return_3d"] = 0.01
    try:
        natural.adapt_records([bad2], {})
    except ValueError:
        pass
    else:
        raise AssertionError("forward leg must be refused")


def test_missing_fields_degrade_safely():
    row = natural.adapt_records([_record(
        decision_timestamp="2020-03-12",
        submitted_orders=(),
        portfolio_before={},
        reward="nan")], {})[0]
    assert row["buy_quantity"] == 0.0
    assert row["names_held"] == 0
    assert row["vix"] is None
    assert row["reward"] == 0.0


def test_vix_asof_join_never_looks_ahead():
    vix_map = {"2020-03-10": 15.0, "2020-03-12": 30.0}
    assert natural.vix_asof(vix_map, "2020-03-11") == 15.0
    assert natural.vix_asof(vix_map, "2020-03-12") == 30.0
    assert natural.vix_asof(vix_map, "2020-03-09") is None
    assert natural.vix_asof({}, "2020-03-12") is None


def test_trigger_matching_and_protection():
    row = {"session": "2020-03-12", "vix": 30.0,
           "unrealized_drawdown": 0.1, "buy_quantity": 2.0,
           "sell_quantity": 0.0, "cash": 1.0, "exposure": 0.1}
    assert natural.match_trigger([["vix", "gt", 25.0]], row) is True
    assert natural.match_trigger([["vix", "gt", 35.0]], row) is False
    assert natural.match_trigger(
        [["drawdown", "gt", 0.05]], row) is True
    assert natural.match_trigger([], row) is True
    rows = [dict(row, session=f"2020-03-{12 + i:02d}") for i in range(3)]
    protected = natural.protected_mask(
        rows, [], "max_quantity", {"cap": 5.0},
        {"kind": "quantity", "normal_quantity": 2.0})
    assert protected == [True, True, True]
    protected = natural.protected_mask(
        rows, [["vix", "gt", 25.0]], "hold_all", {},
        {"kind": "quantity", "normal_quantity": 2.0})
    assert protected == [False, False, False]
    try:
        natural.match_trigger([["mae", "gt", 0.0]], row)
    except ValueError:
        pass
    else:
        raise AssertionError("retrospective trigger field must refuse")


def test_source_contains_no_forbidden_imports():
    import ast
    import pathlib
    source = pathlib.Path(
        "evaluation/repair/natural.py").read_text()
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)) \
                and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant):
            docstrings.add(id(body[0].value))
    # Strip module/function docstrings and the enforcement list itself;
    # every remaining string literal or identifier is live code.
    allowed = {
        # Exact field names refused at runtime (enforcement list itself).
        "forward_return_1d", "forward_return_3d", "mae", "mfe",
        "hold_return", "opportunity_return",
        # Bare tokens of the enforcement tuple above.
        "forward_return", "hold_return", "opportunity", "attribution",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if node.value in allowed:
                continue
            lowered = node.value.lower()
            # String literals outside the enforcement list and docstrings
            # must not name retrospective outcome legs.
            for token in ("forward_return", "mae", "mfe", "hold_return",
                          "opportunity_return", "attribution"):
                assert token not in lowered, (token, node.value)
