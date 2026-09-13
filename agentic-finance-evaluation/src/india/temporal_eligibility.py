"""Strict temporal eligibility: observation vs availability vs decision time.

Separation of concerns (never collapsed):

- CALENDAR (session_resolver): was the venue open?
- OBSERVATION: does a row exist for the observation date?
- AVAILABILITY: when did the information become available?
- DECISION POLICY: at what timestamp does the experiment let the agent act?
- ELIGIBILITY (here): may this observation be exposed at this timestamp?

Rule (strict point-in-time):

- availability known and availability_date <= decision_timestamp
  -> potentially eligible (caller still checks calendar/observation).
- availability known and availability_date > decision_timestamp
  -> ineligible (leakage).
- availability NULL/UNKNOWN and strict PIT required (default)
  -> ineligible. Never assumed.

This module does not weaken ``InformationSet`` (which already rejects NULL
availability). It is the gate *before* InformationSet construction for
datasets whose availability is unknown, and the per-row gate for vintage
datasets. Decision timestamps are always caller-supplied experiment policy;
no universal close/T+1/13:30 default lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Union

import pandas as pd

TimestampLike = Union[str, date, datetime, pd.Timestamp]


def _to_utc_day(value: TimestampLike) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    try:
        if isinstance(value, float) and pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str) and not value.strip():
        return None
    stamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(stamp):
        return None
    return stamp


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason_code: str
    detail: str = ""
    # reason_code in {OK, INFO_UNAVAILABLE, CONSTRAINT_FAIL}


def check_row_eligibility(
    availability_date: object,
    decision_timestamp: TimestampLike,
    *,
    strict: bool = True,
    allow_pre_observation: bool = False,
    observation_date: object = None,
) -> EligibilityDecision:
    """Gate a single observation row against a decision timestamp."""
    decision = _to_utc_day(decision_timestamp)
    if decision is None:
        return EligibilityDecision(
            False, "CONSTRAINT_FAIL", "Decision timestamp is missing/unparseable."
        )
    available = _to_utc_day(availability_date)  # type: ignore[arg-type]
    if available is None:
        if strict:
            return EligibilityDecision(
                False,
                "INFO_UNAVAILABLE",
                "Availability unknown and strict PIT required; ineligible.",
            )
        return EligibilityDecision(
            True, "OK", "Availability unknown but non-strict policy allows."
        )
    if not allow_pre_observation and observation_date is not None:
        observed = _to_utc_day(observation_date)  # type: ignore[arg-type]
        if observed is not None and available < observed:
            return EligibilityDecision(
                False,
                "CONSTRAINT_FAIL",
                "availability_date precedes observation_date (retrospective rule).",
            )
    if available <= decision:
        return EligibilityDecision(True, "OK", "Available at decision time.")
    return EligibilityDecision(
        False,
        "INFO_UNAVAILABLE",
        f"Available {available.date()} after decision {decision.date()}.",
    )


def eligible_frame(
    frame: pd.DataFrame,
    decision_timestamp: TimestampLike,
    *,
    availability_col: str = "availability_date",
    observation_col: Optional[str] = None,
    strict: bool = True,
    allow_pre_observation: bool = False,
) -> pd.DataFrame:
    """Return the subset of rows eligible at the decision timestamp."""
    if availability_col not in frame.columns:
        if strict:
            return frame.iloc[0:0].copy()
        return frame.copy()
    decision = _to_utc_day(decision_timestamp)
    if decision is None:
        return frame.iloc[0:0].copy()
    available = pd.to_datetime(frame[availability_col], errors="coerce", utc=True)
    mask = available.notna() & (available <= decision)
    if strict:
        eligible = frame[mask].copy()
    else:
        eligible = frame[mask | available.isna()].copy()
    if (
        not allow_pre_observation
        and observation_col
        and observation_col in eligible.columns
    ):
        observed = pd.to_datetime(eligible[observation_col], errors="coerce", utc=True)
        eligible = eligible[~(available[eligible.index] < observed)].copy()
    return eligible
