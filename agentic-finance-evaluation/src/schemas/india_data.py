"""Indian Market Data Schemas — V1.0

Pydantic models implementing the Indian Data Contract V1.0.

Design principles:
  - observation_date vs availability_date are ALWAYS distinct fields for
    macro/policy data. The validator rejects availability_date < observation_date.
  - No adjusted prices are manufactured silently — adjusted_close is Optional
    and must be explicitly provided when legitimately available.
  - Gold futures preserve individual contract records. Roll methodology is
    NOT applied here.
  - All models are JSON-serialisable for manifest and audit storage.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DataTier(str, Enum):
    A = "A"          # Tradable assets
    B = "B"          # Market state
    C = "C"          # Exogenous context


class DataFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    EVENT_BASED = "event_based"
    INTRADAY = "intraday"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"


class AcquisitionStatus(str, Enum):
    ACQUIRED = "acquired"
    PENDING_MANUAL_DOWNLOAD = "pending_manual_download"
    ACQUISITION_FAILED = "acquisition_failed"
    NOT_STARTED = "not_started"


class EligibilityStatus(str, Enum):
    NOT_STARTED = "not_started"
    ACQUISITION_PENDING = "acquisition_pending"
    ACQUIRED = "acquired"
    VALIDATED = "validated"
    EXPERIMENT_ELIGIBLE = "experiment_eligible"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Tier A — Equity / Index Records
# ---------------------------------------------------------------------------

class IndianEquityRecord(BaseModel):
    """Security-level daily equity record from NSE.

    Preserves all fields available in NSE Bhavcopy / security-level data.
    adjusted_close must be explicitly provided; it is never manufactured.
    """
    date: date
    symbol: str
    isin: Optional[str] = None
    series: Optional[str] = None           # EQ, BE, SM, etc.
    security_code: Optional[str] = None    # Exchange-specific code

    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    adjusted_close: Optional[float] = None  # Only when legitimately available

    vwap: Optional[float] = None
    traded_quantity: Optional[float] = None
    turnover: Optional[float] = None       # In INR crores or as reported
    number_of_trades: Optional[int] = None
    deliverable_quantity: Optional[float] = None
    delivery_percentage: Optional[float] = None

    source: str = "NSE"
    corporate_action_adjusted: bool = False  # Must be explicitly stated
    notes: Optional[str] = None

    @field_validator("close", "open", "high", "low", "adjusted_close", mode="before")
    @classmethod
    def price_must_be_positive_if_present(cls, v):
        if v is not None and v <= 0:
            raise ValueError(f"Price must be positive, got {v}")
        return v


class IndianIndexRecord(BaseModel):
    """Daily index record (NIFTY 50, NIFTY 500, sector indices).

    PE/PB ratios preserved where available from NSE index analytics.
    """
    date: date
    index_name: str                        # e.g. "NIFTY 50", "NIFTY BANK"
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    points_change: Optional[float] = None
    pct_change: Optional[float] = None
    volume: Optional[float] = None
    turnover: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None

    source: str = "NSE"
    notes: Optional[str] = None

    @field_validator("close", "open", "high", "low", mode="before")
    @classmethod
    def price_must_be_positive_if_present(cls, v):
        if v is not None and v <= 0:
            raise ValueError(f"Index level must be positive, got {v}")
        return v


class IndianVIXRecord(BaseModel):
    """India VIX daily record from NSE.

    India VIX is computed from NIFTY option order book.
    Distinct from CBOE VIX — do NOT treat as equivalent.
    """
    date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    prev_close: Optional[float] = None
    change: Optional[float] = None
    pct_change: Optional[float] = None

    source: str = "NSE"

    @field_validator("close", mode="before")
    @classmethod
    def vix_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f"VIX must be positive, got {v}")
        return v


# ---------------------------------------------------------------------------
# Tier A — Fixed Income Records
# ---------------------------------------------------------------------------

class IndianFixedIncomeRecord(BaseModel):
    """Indian government securities / T-Bill yield record.

    Tenors: 91d, 364d T-Bills; 5Y, 10Y G-Sec benchmark.
    Source: RBI / CCIL / DBIE.
    """
    observation_date: date
    tenor: str                             # e.g. "10Y", "5Y", "91D", "364D"
    yield_pct: Optional[float] = None     # Yield in percentage (e.g. 7.25)
    price: Optional[float] = None         # Clean price where available
    ytm: Optional[float] = None           # Yield to maturity
    coupon: Optional[float] = None

    source: str                            # e.g. "RBI_DBIE", "CCIL", "FBIL"
    source_url: Optional[str] = None
    publication_date: Optional[date] = None  # When the data was published

    notes: Optional[str] = None


class IndianCurrencyRecord(BaseModel):
    """USD/INR exchange rate record.

    Prefer RBI reference rates (FBIL) as the authoritative source.
    """
    date: date
    rate: float                            # INR per 1 USD
    frequency: DataFrequency = DataFrequency.DAILY
    source: str                            # e.g. "RBI_FBIL", "RBI_DBIE"
    source_url: Optional[str] = None
    is_reference_rate: bool = True         # True = official RBI reference rate

    @field_validator("rate", mode="before")
    @classmethod
    def rate_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f"Exchange rate must be positive, got {v}")
        return v


# ---------------------------------------------------------------------------
# Tier A — Gold
# ---------------------------------------------------------------------------

class IndianGoldFuturesRecord(BaseModel):
    """MCX Gold futures individual contract record.

    IMPORTANT: This preserves individual contracts.
    No roll concatenation is applied here.
    The roll methodology must be explicit and documented separately.
    Look-ahead: roll decision must use only information available at roll time.
    """
    trade_date: date
    contract_symbol: str                   # e.g. "GOLDM24JANFUT"
    expiry_date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    settlement_price: Optional[float] = None
    open_interest: Optional[float] = None  # In contracts
    volume: Optional[float] = None        # Contracts traded
    turnover: Optional[float] = None      # In INR lakhs as reported

    source: str = "MCX"
    notes: Optional[str] = None

    @field_validator("close", mode="before")
    @classmethod
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f"Futures price must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def expiry_after_trade_date(self):
        if self.expiry_date < self.trade_date:
            raise ValueError(
                f"expiry_date {self.expiry_date} cannot be before trade_date {self.trade_date}"
            )
        return self


# ---------------------------------------------------------------------------
# Tier B — Market State
# ---------------------------------------------------------------------------

class IndianBreadthRecord(BaseModel):
    """NSE market breadth record.

    Advances/declines for the overall market.
    """
    date: date
    advances: Optional[int] = None
    declines: Optional[int] = None
    unchanged: Optional[int] = None
    advance_decline_ratio: Optional[float] = None

    source: str = "NSE"
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Tier C — Macro / Exogenous Records (CRITICAL: availability_date)
# ---------------------------------------------------------------------------

class IndianMacroRecord(BaseModel):
    """Indian macroeconomic data record.

    CRITICAL DESIGN:
    - observation_date: the reference period the value describes
      (e.g. for CPI, the month whose price level is measured)
    - availability_date: the first date this value would have been
      available to any market participant (i.e. publication/release date)
    - revision_version: '0' = first release, '1' = first revision, etc.

    The agent MUST NOT receive this value before availability_date.
    The evaluator MAY possess future values for scenario labelling,
    but must not leak them into the agent observation.
    """
    observation_date: date
    availability_date: date                # Release date; may be timestamp-normalized
    variable: str                          # e.g. "CPI_COMBINED", "IIP", "REPO_RATE"
    value: float
    unit: Optional[str] = None            # e.g. "percent", "index_2012=100"
    revision_version: int = 0             # 0 = first release
    frequency: DataFrequency = DataFrequency.MONTHLY
    source: str                            # e.g. "MOSPI", "RBI"
    source_url: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def availability_must_be_after_observation(self):
        if self.availability_date < self.observation_date:
            raise ValueError(
                f"availability_date ({self.availability_date}) must not be before "
                f"observation_date ({self.observation_date}). "
                "Retrospective macro records must describe a period already ended."
            )
        return self


class RBIPolicyRecord(BaseModel):
    """RBI policy rate record.

    Event-based series. Rate changes happen at MPC meetings.
    - observation_date: effective date of the rate (when it took effect)
    - availability_date: announcement date (MPC decision date)
    Note: For repo rate, availability typically == observation for same-day effect.
    """
    observation_date: date
    availability_date: date
    announcement_timestamp: Optional[str] = None
    effective_timestamp: Optional[str] = None
    rate_type: str                         # e.g. "REPO", "REVERSE_REPO", "SLR", "CRR"
    rate_pct: float
    change_bps: Optional[float] = None    # Change from previous decision
    stance: Optional[str] = None          # e.g. "accommodative", "neutral", "withdrawal"
    source: str = "RBI"
    source_url: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_policy_dates(self):
        # An MPC announcement can precede the effective date.  Policy data
        # therefore preserves both dates rather than applying the macro rule
        # used for retrospective CPI/IIP observations.
        return self


# ---------------------------------------------------------------------------
# Crude Oil (Exogenous Context — Non-Indian tradable)
# ---------------------------------------------------------------------------

class CrudeOilRecord(BaseModel):
    """Crude oil price record (exogenous context, not Indian tradable asset).

    Source is explicitly non-Indian (EIA, ICE, etc.).
    Used only as exogenous context variable.
    """
    date: date
    benchmark: str                         # e.g. "BRENT", "WTI", "MCX_CRUDE"
    price_usd: Optional[float] = None     # USD per barrel
    price_inr: Optional[float] = None     # INR per barrel if converted
    source: str
    source_is_indian: bool = False         # Explicitly mark as non-Indian
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Dataset Manifest Schema
# ---------------------------------------------------------------------------

class MissingSummaryField(BaseModel):
    """Per-field missingness statistics."""
    field_name: str
    missing_count: int
    total_count: int
    missing_pct: float


class RawArtifactProvenance(BaseModel):
    """Provenance for one raw file in a multi-file acquisition.

    Single-file datasets continue to use ``raw_path``/``raw_sha256``.
    Multi-file acquisitions (e.g. annual NSE downloads) populate
    ``raw_paths`` plus one entry per file here, preserving byte size and
    row counts without rewriting raw evidence.
    """
    path: str
    sha256: str
    byte_size: Optional[int] = None
    row_count: Optional[int] = None


class DatasetManifest(BaseModel):
    """Machine-readable manifest for one acquired dataset.

    Written to data/manifests/india/<dataset_id>.yaml.
    SHA-256 hashes are deterministic and allow reproducibility verification.
    """
    dataset_id: str
    tier: DataTier
    asset_class: str                       # e.g. "equity", "fixed_income", "macro"
    variable: str                          # e.g. "NIFTY50_DAILY", "CPI_COMBINED"

    source_institution: str               # e.g. "NSE", "RBI", "MOSPI", "MCX"
    source_url: Optional[str] = None
    retrieval_timestamp: Optional[str] = None  # ISO 8601 UTC

    raw_path: Optional[str] = None
    raw_sha256: Optional[str] = None

    # Smallest principled multi-artifact extension: raw acquisition may
    # consist of several files (e.g. annual NSE downloads). When populated,
    # raw_paths lists every artifact and raw_artifacts carries per-file
    # SHA-256 provenance. Single-file manifests are unaffected.
    raw_paths: Optional[List[str]] = None
    raw_artifacts: Optional[List[RawArtifactProvenance]] = None

    processing_version: str = "1.0.0"
    processing_parameters: Dict[str, Any] = Field(default_factory=dict)

    processed_path: Optional[str] = None
    processed_sha256: Optional[str] = None

    frequency: DataFrequency
    earliest_observation: Optional[str] = None   # ISO date
    latest_observation: Optional[str] = None     # ISO date
    row_count: Optional[int] = None
    unique_date_count: Optional[int] = None
    duplicate_count: Optional[int] = None

    has_observation_date: bool = False
    has_availability_date: bool = False     # True for macro/policy records

    missingness_summary: List[MissingSummaryField] = Field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.PENDING
    acquisition_status: AcquisitionStatus = AcquisitionStatus.NOT_STARTED
    eligibility_status: EligibilityStatus = EligibilityStatus.NOT_STARTED

    notes: Optional[str] = None

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for YAML writing."""
        return json.loads(self.model_dump_json())

    @staticmethod
    def required_fields() -> List[str]:
        return [
            "dataset_id", "tier", "asset_class", "variable",
            "source_institution", "frequency", "validation_status",
            "acquisition_status",
        ]
