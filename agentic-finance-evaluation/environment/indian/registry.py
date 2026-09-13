"""Explicit registry of the 10 canonical-asset specifications.

Dataset IDs, manifest IDs, paths, and schemas reuse the repository's
existing canonical identifiers exactly. No new canonical identifiers are
invented here.

Venue choices follow existing implementation semantics: NIFTY 50 and
India VIX are NSE-session assets (the coverage auditor and calendar tests
already gate them on the NSE calendar), so they share venue NSE_CM with
NSE equities. USD/INR is gated as a publication series
(requires_calendar=False) because the RBI_FX venue has no acquired
Mumbai-holiday day map; forcing the venue gate would mark every FX slot
CAL_UNKNOWN. This is documented on the spec, not inferred.
"""

from __future__ import annotations

from typing import Dict, List

from environment.indian.asset_contract import (
    AssetSpec,
    CLASS_COMMODITY,
    CLASS_CURRENCY,
    CLASS_EQUITY,
    CLASS_EXOGENOUS,
    CLASS_INDEX,
    CLASS_MACRO,
    CLASS_POLICY,
    CLASS_RATE,
    CLASS_VOLATILITY,
    ROLE_INDICATOR,
    ROLE_INFORMATION,
    ROLE_TRADEABLE,
)

ASSET_REGISTRY: Dict[str, AssetSpec] = {}


def _register(spec: AssetSpec) -> AssetSpec:
    errors = spec.validate()
    if errors:
        raise ValueError(f"invalid AssetSpec {spec.asset_id}: {errors}")
    if spec.asset_id in ASSET_REGISTRY:
        raise ValueError(f"duplicate asset_id {spec.asset_id!r}")
    ASSET_REGISTRY[spec.asset_id] = spec
    return spec


_register(AssetSpec(
    asset_id="nse_equity",
    asset_class=CLASS_EQUITY,
    venue="NSE_CM",
    source="NSE",
    manifest_id="nse_equity_bhavcopy_daily",
    csv_path="data/processed/india/equities/nse_equity_daily.csv",
    observation_col="observation_date",
    availability_col="availability_date",  # 100% NULL by design (unknown)
    frequency="daily",
    requires_calendar=True,
    tradable=True,
    role=ROLE_TRADEABLE,
    price_fields=("close", "last_price", "vwap"),
    units="INR per share",
    id_cols=("symbol", "series"),
    notes="Security-level bhavcopy. Tradable universe is config-explicit; "
          "availability stays NULL so the observation-lag path applies.",
))

_register(AssetSpec(
    asset_id="nifty50",
    asset_class=CLASS_INDEX,
    venue="NSE_CM",
    source="NSE",
    manifest_id="nse_nifty_50_daily",
    csv_path="data/processed/india/market/nse_nifty_50_daily.csv",
    observation_col="date",
    availability_col=None,  # no availability column in canonical data
    frequency="daily",
    requires_calendar=True,
    tradable=False,
    role=ROLE_INDICATOR,
    price_fields=("close",),
    units="index points",
    notes="Market indicator only; not actionable through the action interface.",
))

_register(AssetSpec(
    asset_id="indiavix",
    asset_class=CLASS_VOLATILITY,
    venue="NSE_CM",
    source="NSE",
    manifest_id="nse_india_vix_daily",
    csv_path="data/processed/india/market/nse_india_vix_daily.csv",
    observation_col="date",
    availability_col=None,
    frequency="daily",
    requires_calendar=True,
    tradable=False,
    role=ROLE_INDICATOR,
    price_fields=("close",),
    units="annualised volatility points",
    notes="Market indicator only; not actionable through the action interface.",
))

_register(AssetSpec(
    asset_id="mcx_gold",
    asset_class=CLASS_COMMODITY,
    venue="MCX",
    source="MCX",
    manifest_id="mcx_gold_futures_individual_contracts",
    csv_path="data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv",
    observation_col="trade_date",
    availability_col=None,
    frequency="daily",
    requires_calendar=True,
    tradable=True,
    role=ROLE_TRADEABLE,
    price_fields=("close", "settlement_price"),
    units="INR per 10g (contract terms)",
    id_cols=("contract_symbol",),
    notes="Contract-level futures. Named contracts from config only; no "
          "continuous series is constructed here.",
))

_register(AssetSpec(
    asset_id="usd_inr",
    asset_class=CLASS_CURRENCY,
    venue="RBI_FX",
    source="RBI",
    manifest_id="rbi_usd_inr_daily",
    csv_path="data/processed/india/market/rbi_usd_inr_daily.csv",
    observation_col="date",
    availability_col=None,
    frequency="daily",
    requires_calendar=False,  # decided: no Mumbai-holiday map; PIT-gated series
    tradable=False,
    role=ROLE_INDICATOR,
    price_fields=("rate",),
    units="INR per USD",
    notes="RBI reference rate, ~13:30 IST publication rule. Calendar gating "
          "disabled explicitly: RBI_FX day map unacquired, so venue gating "
          "would mark every slot CAL_UNKNOWN. Observation-lag path applies.",
))

_register(AssetSpec(
    asset_id="gsec10y",
    asset_class=CLASS_RATE,
    venue="RBI_GSEC",
    source="RBI",
    manifest_id="rbi_gsec_10y_yield",
    csv_path="data/processed/india/market/rbi_gsec_10y_weekly.csv",
    observation_col="observation_date",
    availability_col=None,
    frequency="weekly",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("yield_pct",),
    units="percent per annum",
    notes="Friday observation weeks. Observation Friday != availability "
          "Friday; observation-lag path exposes only strictly prior weeks.",
))

_register(AssetSpec(
    asset_id="tbill91d",
    asset_class=CLASS_RATE,
    venue="RBI_GSEC",
    source="RBI",
    manifest_id="rbi_gsec_91d_yield",
    csv_path="data/processed/india/market/rbi_tbill_91d_weekly.csv",
    observation_col="observation_date",
    availability_col=None,
    frequency="weekly",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("yield_pct",),
    units="percent per annum",
    notes="Same weekly observation-lag semantics as gsec10y.",
))

_register(AssetSpec(
    asset_id="tbill364d",
    asset_class=CLASS_RATE,
    venue="RBI_GSEC",
    source="RBI",
    manifest_id="rbi_gsec_364d_yield",
    csv_path="data/processed/india/market/rbi_tbill_364d_weekly.csv",
    observation_col="observation_date",
    availability_col=None,
    frequency="weekly",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("yield_pct",),
    units="percent per annum",
    notes="Same weekly observation-lag semantics as gsec10y.",
))

_register(AssetSpec(
    asset_id="rbi_policy",
    asset_class=CLASS_POLICY,
    venue="RBI_POLICY",
    source="RBI",
    manifest_id="rbi_policy_rate_events",
    csv_path="data/processed/india/macro/rbi_policy_rate_events.csv",
    observation_col="observation_date",
    availability_col="availability_date",
    frequency="event_based",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("rate_pct",),
    units="percent per annum",
    lookup_path="vintage_pit",
    allow_pre_observation=True,  # announcement may precede effective date
    notes="Event-based InformationSet path keyed on announcement "
          "availability; effective date never grants early visibility.",
))

_register(AssetSpec(
    asset_id="cpi",
    asset_class=CLASS_MACRO,
    venue="MOSPI",
    source="MOSPI",
    manifest_id="mospi_cpi_combined_monthly",
    csv_path="data/processed/india/macro/mospi_cpi_combined_monthly.csv",
    observation_col="observation_date",
    availability_col="availability_date",
    frequency="monthly",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("cpi_index",),
    units="index 2012=100",
    lookup_path="vintage_pit",
    notes="Monthly vintage path via InformationSet; unverified (NULL "
          "availability) vintages are INFO_UNAVAILABLE, never eligible.",
))

_register(AssetSpec(
    asset_id="iip",
    asset_class=CLASS_MACRO,
    venue="MOSPI",
    source="MOSPI",
    manifest_id="mospi_iip_general_monthly",
    csv_path="data/processed/india/macro/mospi_iip_general_monthly.csv",
    observation_col="observation_date",
    availability_col="availability_date",
    frequency="monthly",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("iip_index",),
    units="index 2011-12=100",
    lookup_path="vintage_pit",
    notes="Monthly vintage path via InformationSet with Statement I union "
          "reconciliation preserved upstream.",
))

_register(AssetSpec(
    asset_id="brent",
    asset_class=CLASS_EXOGENOUS,
    venue="EIA",
    source="EIA",
    manifest_id="crude_oil_brent_daily",
    csv_path="data/processed/india/crude/eia_rbrte_brent_spot_daily.csv",
    observation_col="observation_date",
    availability_col="availability_date",  # 100% NULL: unknown history
    frequency="daily",
    requires_calendar=False,
    tradable=False,
    role=ROLE_INFORMATION,
    price_fields=("brent_spot_usd_bbl",),
    units="USD per barrel",
    lookup_path="vintage_pit",
    notes="Global exogenous input. Availability unknown for every row, so "
          "strict PIT keeps Brent INFO_UNAVAILABLE. Never NSE-forced.",
))


def get_spec(asset_id: str) -> AssetSpec:
    try:
        return ASSET_REGISTRY[asset_id]
    except KeyError:
        raise ValueError(
            f"unknown asset_id {asset_id!r}; registered: {sorted(ASSET_REGISTRY)}"
        )


def list_specs() -> List[AssetSpec]:
    return [ASSET_REGISTRY[k] for k in sorted(ASSET_REGISTRY)]
