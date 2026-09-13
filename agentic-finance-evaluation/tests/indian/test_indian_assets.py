"""A. Asset contract + B. Asset registration tests."""

import pytest

from environment.indian.asset_contract import (
    AssetSpec,
    ROLE_INDICATOR,
    ROLE_INFORMATION,
    ROLE_TRADEABLE,
)
from environment.indian.registry import ASSET_REGISTRY, get_spec, list_specs


def test_registry_covers_all_twelve_asset_ids():
    assert sorted(ASSET_REGISTRY) == [
        "brent", "cpi", "gsec10y", "iip", "indiavix", "mcx_gold",
        "nifty50", "nse_equity", "rbi_policy", "tbill364d", "tbill91d",
        "usd_inr",
    ]


def test_contract_fields_are_explicit():
    for spec in list_specs():
        assert spec.validate() == [], spec.asset_id
        assert spec.asset_id and spec.venue and spec.csv_path
        assert spec.observation_col and spec.frequency and spec.source


def test_role_separation_tradable_indicator_information():
    tradeable = {s.asset_id for s in list_specs() if s.tradable}
    assert tradeable == {"nse_equity", "mcx_gold"}
    for s in list_specs():
        if s.tradable:
            assert s.role == ROLE_TRADEABLE
        elif s.asset_id in ("nifty50", "indiavix", "usd_inr"):
            assert s.role == ROLE_INDICATOR
        else:
            assert s.role == ROLE_INFORMATION


def test_information_assets_are_not_tradable():
    for aid in ("cpi", "iip", "rbi_policy", "gsec10y", "tbill91d",
                "tbill364d", "brent", "nifty50", "indiavix", "usd_inr"):
        assert get_spec(aid).tradable is False


def test_calendar_applicability_is_explicit_per_asset():
    assert get_spec("nse_equity").requires_calendar is True
    assert get_spec("mcx_gold").requires_calendar is True
    assert get_spec("cpi").requires_calendar is False
    assert get_spec("iip").requires_calendar is False
    assert get_spec("rbi_policy").requires_calendar is False
    assert get_spec("brent").requires_calendar is False


def test_unknown_asset_registration_lookup_fails():
    with pytest.raises(ValueError, match="unknown asset_id"):
        get_spec("nonsense_asset")


def test_contract_validation_rejects_bad_specs():
    bad = AssetSpec(
        asset_id="bad", asset_class="X", venue="V", source="S",
        manifest_id="m", csv_path="p", observation_col="o",
        availability_col=None, frequency="daily",
        requires_calendar=True, tradable=True, role=ROLE_INFORMATION)
    assert bad.validate() != []
