"""Explicit asset specification contract for the multi-asset Indian environment.

Every property is declared, never inferred from missing data. In particular
``requires_calendar`` and ``tradable`` are explicit per-asset configuration:
publication/event assets are NOT forced through exchange-session calendars,
and information assets can NEVER be traded through the action interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

# Asset roles. Exactly one per asset.
ROLE_TRADEABLE = "TRADEABLE"
ROLE_INDICATOR = "INDICATOR"
ROLE_INFORMATION = "INFORMATION"

ROLES = (ROLE_TRADEABLE, ROLE_INDICATOR, ROLE_INFORMATION)

# Asset classes present in the canonical Indian datasets.
CLASS_EQUITY = "EQUITY"
CLASS_INDEX = "INDEX"
CLASS_VOLATILITY = "VOLATILITY"
CLASS_CURRENCY = "CURRENCY"
CLASS_COMMODITY = "COMMODITY"
CLASS_RATE = "RATE"
CLASS_POLICY = "POLICY"
CLASS_MACRO = "MACRO"
CLASS_EXOGENOUS = "EXOGENOUS"


@dataclass(frozen=True)
class AssetSpec:
    """Static, explicit contract for one environment asset."""

    asset_id: str
    asset_class: str
    venue: str
    source: str
    manifest_id: str
    csv_path: str
    # Observation timestamp semantics: column holding the date/period the
    # observation belongs to (observation time, never availability time).
    observation_col: str
    # Availability timestamp semantics: column holding first availability,
    # or None when the canonical dataset carries no availability column.
    # None + strict PIT means the observation-lag path applies (see
    # information_lookup); it never means "assume available".
    availability_col: Optional[str]
    frequency: str  # daily | weekly | monthly | event_based
    # requires_calendar is explicit (never inferred): True only for assets
    # whose venue session determines whether an observation can exist.
    requires_calendar: bool
    tradable: bool
    role: str
    # Price/value fields in priority order; the first non-null is the mark.
    price_fields: Tuple[str, ...] = ("close",)
    units: str = ""
    # Vintage semantics: how multiple rows per observation period are
    # resolved. Consumed by information_lookup; "explicit" means the caller
    # supplies the policy per lookup (fail-loud on ambiguity).
    vintage_policy: str = "explicit"
    allow_pre_observation: bool = False
    # Identity columns selecting one instrument series (e.g. equity symbol /
    # series, gold contract_symbol). Empty for single-series assets.
    id_cols: Tuple[str, ...] = ()
    # Lookup path: how information_lookup resolves visibility.
    # - "observation_lag": latest row with observation key strictly before
    #   the decision timestamp (explicit >=1-day publication-lag assumption;
    #   no intraday timing claimed). Used when the canonical dataset carries
    #   no usable availability column.
    # - "vintage_pit": InformationSet latest-eligible-vintage path driven by
    #   the availability column. Rows with NULL availability are dropped
    #   before InformationSet construction and stay INFO_UNAVAILABLE.
    lookup_path: str = "observation_lag"
    notes: str = ""

    def validate(self) -> list:
        errors = []
        if not self.asset_id:
            errors.append("asset_id must be non-empty")
        if self.role not in ROLES:
            errors.append(f"unknown role {self.role!r}")
        if not self.venue:
            errors.append("venue must be explicit")
        if not self.csv_path:
            errors.append("csv_path must be explicit")
        if not self.observation_col:
            errors.append("observation_col must be explicit")
        if self.tradable and self.role != ROLE_TRADEABLE:
            errors.append("only ROLE_TRADEABLE assets may be tradable")
        if self.role == ROLE_TRADEABLE and not self.tradable:
            errors.append("ROLE_TRADEABLE assets must be tradable")
        if self.vintage_policy not in ("explicit", "earliest_available", "latest_available"):
            errors.append(f"unknown vintage_policy {self.vintage_policy!r}")
        if self.lookup_path not in ("observation_lag", "vintage_pit"):
            errors.append(f"unknown lookup_path {self.lookup_path!r}")
        return errors
