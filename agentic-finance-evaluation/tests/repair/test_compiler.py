"""Tier 1: compiler mappings, UNCOMPILABLE discipline, M-R3 reservation."""

import pytest

from evaluation.repair.compiler import Uncompilable, compile
from evaluation.repair.schemas import APPROVED_RULE_TYPES
from tests.repair.helpers import make_mechanism


def test_concentration_maps_to_exposure_cap():
    spec = compile(make_mechanism(taxonomy="concentration"), "spec-001")
    assert spec.rule_type == "exposure_cap"
    assert spec.rule() == {"type": "exposure_cap", "max_names_held": 1}
    assert spec.mechanism_fingerprint


def test_turnover_family_maps_to_order_cap():
    for taxonomy in ("turnover", "accumulation", "risk", "leverage",
                     "Risk/Sizing"):
        spec = compile(make_mechanism(taxonomy=taxonomy), "spec-x")
        assert spec.rule_type == "per_session_order_cap", taxonomy
        assert spec.rule_params == {"max_orders": 1}


def test_volatility_requires_regime_trigger():
    vix_trigger = (("vix", "gt", 25.0),)
    spec = compile(
        make_mechanism(taxonomy="volatility", trigger_hint=vix_trigger),
        "spec-v")
    assert spec.rule_type == "hold_all"
    assert spec.trigger == vix_trigger
    refused = compile(make_mechanism(taxonomy="volatility"), "spec-v2")
    assert isinstance(refused, Uncompilable)
    assert "regime trigger" in refused.reason
    refused_exec = compile(make_mechanism(taxonomy="Execution"), "spec-v3")
    assert isinstance(refused_exec, Uncompilable)


def test_unknown_taxonomy_is_uncompilable():
    result = compile(make_mechanism(taxonomy="sentiment-alpha"), "spec-u")
    assert isinstance(result, Uncompilable)
    assert result.mechanism_id == "mech-001"
    assert result.compiler_version == "v1"


def test_mr3_loss_chasing_maps_to_max_quantity():
    # M-R3 authorised extension: loss-chasing compiles to a bounded
    # quantity ceiling whose cap comes pre-registered from scope_hint.
    spec = compile(
        make_mechanism(taxonomy="loss-chasing",
                       scope_hint={"max_quantity_cap": 5.0}),
        "spec-lc")
    assert spec.rule_type == "max_quantity"
    assert spec.rule() == {"type": "max_quantity", "cap": 5.0}
    missing = compile(make_mechanism(taxonomy="loss-chasing"), "spec-lc2")
    from evaluation.repair.compiler import Uncompilable
    assert isinstance(missing, Uncompilable)
    assert "pre-registered" in missing.reason


def test_repair_spec_rejects_unknown_rule_type():
    with pytest.raises(ValueError):
        from evaluation.repair.schemas import RepairSpec
        RepairSpec(spec_id="s", mechanism_fingerprint="m",
                   rule_type="quantum-throttle",
                   rule_params={})


def test_scope_hint_flows_into_spec():
    spec = compile(
        make_mechanism(
            taxonomy="concentration",
            scope_hint={"agent_id": "stub-agent",
                        "instruments": ["RELIANCE:EQ"],
                        "vix_band": [20.0, 40.0]}),
        "spec-s")
    assert spec.scope.agent_id == "stub-agent"
    assert spec.scope.instruments == ("RELIANCE:EQ",)
    assert spec.scope.vix_band == (20.0, 40.0)
    assert spec.priority == 0
    prioritised = compile(make_mechanism(taxonomy="turnover"), "spec-p",
                          priority=3)
    assert prioritised.priority == 3


def test_compiler_rejects_non_mechanism():
    with pytest.raises(TypeError):
        compile({"taxonomy": "turnover"}, "spec-bad")
