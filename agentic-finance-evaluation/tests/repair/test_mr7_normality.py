"""M-R7 normality specification tests (additive, no environment runs)."""

from evaluation.repair.normality import (
    SPECIFICATIONS,
    annotate_exposure_active,
)


def _row(vix=None, active=False):
    return {"session": "2020-03-12", "vix": vix,
            "exposure_active": active, "buy_quantity": 2.0,
            "sell_quantity": 0.0}


def test_n0_is_regime_protected():
    spec = SPECIFICATIONS["N0"]
    assert spec.protected_session(_row(vix=12.0, active=True), "exposure")
    assert not spec.protected_session(_row(vix=30.0, active=True),
                                      "exposure")
    assert not spec.protected_session(_row(vix=30.0, active=False),
                                      "exposure")


def test_n1_is_mechanism_relative():
    spec = SPECIFICATIONS["N1"]
    assert spec.protected_session(_row(vix=30.0, active=False),
                                  "exposure")
    assert not spec.protected_session(_row(vix=30.0, active=True),
                                      "exposure")
    assert not spec.protected_session(_row(vix=12.0, active=True),
                                      "exposure")


def test_n2_is_hybrid():
    spec = SPECIFICATIONS["N2"]
    assert spec.protected_session(_row(vix=12.0, active=False),
                                  "exposure")
    assert not spec.protected_session(_row(vix=12.0, active=True),
                                      "exposure")
    assert not spec.protected_session(_row(vix=30.0, active=False),
                                      "exposure")
    assert not spec.protected_session(_row(vix=30.0, active=True),
                                      "exposure")


def test_missing_fields_fail_closed():
    for spec in SPECIFICATIONS.values():
        assert spec.protected_session({}, "exposure") is True
        assert spec.protected_session({"vix": "bad"}, "exposure") is True


def test_fingerprints_deterministic_and_distinct():
    prints = {k: s.fingerprint() for k, s in SPECIFICATIONS.items()}
    assert len(set(prints.values())) == 3
    assert all(len(v) == 64 for v in prints.values())
    audit = SPECIFICATIONS["N1"].audit()
    assert audit["specification_id"] == "N1"
    assert audit["fingerprint"] == prints["N1"]


def test_annotate_exposure_active_deterministic():
    rows = [{"session": f"s{i}", "names_held": n}
            for i, n in enumerate([0, 1, 2, 3, 5])]
    first = annotate_exposure_active(rows, 2)
    second = annotate_exposure_active(rows, 2)
    assert [r["exposure_active"] for r in first] == [
        False, False, False, True, True]
    assert first == second
    # Original rows never mutated.
    assert all("exposure_active" not in r for r in rows)


def test_signature_excludes_forbidden_inputs():
    import inspect
    import evaluation.repair.normality as module
    # Interface proof: protected_session accepts exactly
    # (record, mechanism) — no channel for outcomes exists.
    params = list(inspect.signature(
        SPECIFICATIONS["N0"].protected_session).parameters)
    assert params == ["record", "mechanism"]
    for name in ("annotate_exposure_active",):
        params = list(inspect.signature(
            getattr(module, name)).parameters)
        assert "heldout" not in params and "held_out" not in params
    # Behavioural proof: forbidden-ish extra fields cannot change
    # the verdict (they are never read).
    base = {"session": "s", "vix": 30.0, "exposure_active": True}
    spiked = dict(base, pnl=999.0, sharpe=5.0,
                  forward_return=0.5, heldout="x",
                  candidate_results=[{"effect": -100.0}])
    for spec in SPECIFICATIONS.values():
        assert spec.protected_session(spiked, "exposure") == \
            spec.protected_session(base, "exposure")
