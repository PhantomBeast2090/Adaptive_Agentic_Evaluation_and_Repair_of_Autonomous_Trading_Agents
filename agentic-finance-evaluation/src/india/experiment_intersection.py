"""Per-experiment common temporal intersection with reason codes.

There is no permanent global intersection. Each experiment derives its own
date set from:

    required_assets (each bound to a venue + observation/availability source)
    start_date / end_date
    decision-timing policy (how decision_timestamp is derived per date)

Layer separation (never collapsed):

    CALENDAR: session/trading eligibility (SessionResolver). Applies ONLY
        to assets with requires_calendar=True (exchange-traded venues).
        Publication/event assets (CPI, IIP, policy, G-Sec, Brent) set
        requires_calendar=False and are gated on observation existence +
        availability/PIT only; they are never forced through an
        exchange-session calendar.
    TEMPORAL ELIGIBILITY: information availability relative to the
        caller-supplied decision timestamp (temporal_eligibility).
    VINTAGE SELECTION: which version of an observation is visible. Done
        UPSTREAM via InformationSet or an explicit availability_policy;
        this layer only consumes the resulting effective availability.
    EXPERIMENT INTERSECTION (here): derives the date set after applying
        the experiment's explicitly declared calendar + observation +
        availability policies.

For every date in [start, end] the derivation records exactly one reason:

    OK               every required asset has an observation AND is
                     temporally eligible AND calendar permits trading
    OBS_MISSING      at least one required asset has no observation
    INFO_UNAVAILABLE at least one observation exists but was not yet
                     available at the decision timestamp (or availability
                     unknown under strict PIT)
    CAL_UNKNOWN      calendar state unknown for a required venue
    CAL_CLOSED       required venue closed/holiday with no special session
    CONSTRAINT_FAIL  any other explicit constraint (e.g. conflict, half-day
                     without handling, unparseable timestamp)

No silent date deletion: ``excluded`` carries one entry per dropped date
with its reason, asset, venue, calendar state, and availability state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Dict, List, Mapping, Optional, Set

import pandas as pd

from src.india.session_resolver import SessionResolver
from src.india.temporal_eligibility import check_row_eligibility

REASON_CODES = (
    "OK",
    "OBS_MISSING",
    "INFO_UNAVAILABLE",
    "CAL_UNKNOWN",
    "CAL_CLOSED",
    "CONSTRAINT_FAIL",
)


@dataclass(frozen=True)
class AssetRequirement:
    """One required asset and how to test it for a date.

    ``requires_calendar`` declares explicitly whether the venue's
    market-session calendar gates this asset. It is NEVER inferred from
    asset class, venue name, calendar-row presence, weekdays, source, or
    missing observations:

    - requires_calendar=True (default, backward compatible): exchange-traded
      assets (NSE equity/indices, MCX). The SessionResolver gate applies
      exactly as before (CONFLICT->CONSTRAINT_FAIL, UNKNOWN->CAL_UNKNOWN,
      CLOSED->CAL_CLOSED, OPEN/SPECIAL->continue).
    - requires_calendar=False: publication/event/source-calendar assets
      (CPI, IIP, policy events, G-Sec series, Brent). The resolver is NOT
      consulted, no CAL_UNKNOWN is produced for the venue, and no
      OPEN/CLOSED is inferred. Observation-existence and strict
      availability/PIT checks still apply unchanged.
    """

    asset_id: str
    venue: str
    # observation_dates: the set of dates with at least one observation row.
    observation_dates: frozenset
    # availability_by_date: observation date -> availability date (or None).
    # For vintage (multi-row) assets, callers pass the *effective*
    # availability relevant to the experiment (e.g. latest eligible vintage
    # rule applied upstream); per-row gating stays in temporal_eligibility.
    availability_by_date: Mapping[str, object] = field(default_factory=dict)
    allow_pre_observation: bool = False
    # Optional observation-period mapping for monthly assets: trading date ->
    # owning observation key. When None, key == trading date ISO string.
    observation_key: Optional[Callable[[date], Optional[str]]] = None
    # Explicit calendar applicability. Default True preserves the legacy
    # behavior for exchange-traded requirements; publication-based assets
    # must explicitly opt out with requires_calendar=False.
    requires_calendar: bool = True


@dataclass(frozen=True)
class ExcludedDate:
    calendar_date: date
    reason_code: str
    asset_id: str = ""
    venue: str = ""
    calendar_state: str = ""
    availability_state: str = ""
    detail: str = ""


@dataclass
class IntersectionResult:
    experiment_id: str
    required_assets: List[str]
    start_date: date
    end_date: date
    included: List[date]
    excluded: List[ExcludedDate]
    notes: List[str] = field(default_factory=list)

    @property
    def total_common_days(self) -> int:
        return len(self.included)


DecisionPolicy = Callable[[date], object]


def default_decision_policy(day: date) -> date:
    """Identity policy: decide on the date itself (date grain).

    Experiments may supply any stricter policy (e.g. next trading day,
    fixed lag). The calendar never hard-codes one.
    """
    return day


def derive_intersection(
    *,
    experiment_id: str,
    requirements: List[AssetRequirement],
    start: date,
    end: date,
    resolver: SessionResolver,
    decision_policy: DecisionPolicy = default_decision_policy,
    strict: bool = True,
    require_open_calendar: bool = True,
) -> IntersectionResult:
    if start > end:
        raise ValueError("Intersection start must not be after end.")
    included: List[date] = []
    excluded: List[ExcludedDate] = []
    notes: List[str] = []
    day = start
    while day <= end:
        decision_timestamp = decision_policy(day)
        day_excluded: Optional[ExcludedDate] = None
        for req in requirements:
            # 1. Calendar gate for the required venue (only when the asset
            # explicitly requires session-calendar gating). Publication /
            # event assets (requires_calendar=False) skip the resolver
            # entirely: no CAL_UNKNOWN, no OPEN/CLOSED inference.
            if req.requires_calendar:
                resolution = resolver.resolve(req.venue, day)
            else:
                resolution = None
            if resolution is not None:
                if resolution.market_status == "CONFLICT":
                    day_excluded = ExcludedDate(
                        day, "CONSTRAINT_FAIL", req.asset_id, req.venue,
                        "CONFLICT", "", "Conflicting calendar evidence.",
                    )
                    break
                if resolution.market_status == "UNKNOWN":
                    day_excluded = ExcludedDate(
                        day, "CAL_UNKNOWN", req.asset_id, req.venue,
                        "UNKNOWN", "", "No calendar evidence for venue/date.",
                    )
                    break
                if require_open_calendar and resolution.market_status == "CLOSED":
                    day_excluded = ExcludedDate(
                        day, "CAL_CLOSED", req.asset_id, req.venue,
                        resolution.session_type, "", "Venue closed/holiday.",
                    )
                    break
                if require_open_calendar and resolution.market_status == "HALF_DAY":
                    day_excluded = ExcludedDate(
                        day, "CONSTRAINT_FAIL", req.asset_id, req.venue,
                        "HALF_DAY", "",
                        "Half-day session has no approved handling in this policy.",
                    )
                    break
                calendar_state = resolution.market_status
            else:
                calendar_state = "SKIPPED"
            # 2. Observation gate.
            key = req.observation_key(day) if req.observation_key else day.isoformat()
            if key is None or key not in req.observation_dates:
                day_excluded = ExcludedDate(
                    day, "OBS_MISSING", req.asset_id, req.venue,
                    calendar_state, "",
                    f"No observation for key {key}.",
                )
                break
            # 3. Availability gate at the decision timestamp.
            availability = req.availability_by_date.get(key) if req.availability_by_date else None
            # Assets with no availability column at all: availability None.
            verdict = check_row_eligibility(
                availability,
                decision_timestamp,
                strict=strict,
                allow_pre_observation=req.allow_pre_observation,
            )
            if not verdict.eligible:
                code = verdict.reason_code if verdict.reason_code in (
                    "INFO_UNAVAILABLE", "CONSTRAINT_FAIL") else "INFO_UNAVAILABLE"
                day_excluded = ExcludedDate(
                    day, code, req.asset_id, req.venue,
                    calendar_state,
                    "NULL" if availability is None else str(availability),
                    verdict.detail,
                )
                break
        if day_excluded is None:
            included.append(day)
        else:
            excluded.append(day_excluded)
        day += timedelta(days=1)
    notes.append(
        f"{experiment_id}: {len(included)} included, {len(excluded)} excluded "
        f"over {start}..{end} for {[r.asset_id for r in requirements]}."
    )
    return IntersectionResult(
        experiment_id=experiment_id,
        required_assets=[r.asset_id for r in requirements],
        start_date=start,
        end_date=end,
        included=included,
        excluded=excluded,
        notes=notes,
    )


AVAILABILITY_POLICIES = (
    "earliest_available",
    "latest_available",
    "explicit",
)


def build_requirement_from_frame(
    *,
    asset_id: str,
    venue: str,
    frame: pd.DataFrame,
    observation_col: str,
    availability_col: Optional[str] = None,
    allow_pre_observation: bool = False,
    requires_calendar: bool = True,
    availability_policy: Optional[str] = None,
) -> AssetRequirement:
    """Build an AssetRequirement from a canonical dataframe.

    observation_dates holds ISO date keys present in the frame.

    Vintage policy (never silent). When several distinct non-null
    availability values exist for one observation key (multi-vintage
    assets such as CPI/IIP), the caller must choose explicitly:

    - "earliest_available": earliest non-null availability per key
      ("when did this information first become available?").
    - "latest_available": latest non-null availability per key. Use only
      when the experiment explicitly wants the latest vintage.
    - "explicit" (or None, the default): NO aggregation is performed. A
      single distinct availability per key works as-is; multiple distinct
      values raise ValueError naming the key. The caller must then either
      pick a policy above or supply an already-vintage-filtered mapping
      directly via AssetRequirement (e.g. from InformationSet upstream:
      raw canonical dataset -> vintage selection / InformationSet ->
      effective availability -> experiment intersection).

    NULL-only keys stay NULL and remain strict-PIT-ineligible.
    """
    if availability_policy is not None and availability_policy not in AVAILABILITY_POLICIES:
        raise ValueError(
            f"Unknown availability_policy {availability_policy!r}; "
            f"expected one of {AVAILABILITY_POLICIES}."
        )
    obs = pd.to_datetime(frame[observation_col], errors="coerce").dt.date
    keys = {d.isoformat() for d in obs.dropna().unique()}
    avail_map: Dict[str, object] = {}
    if availability_col and availability_col in frame.columns:
        avail = pd.to_datetime(frame[availability_col], errors="coerce")
        tmp = pd.DataFrame({"k": obs.astype(str), "a": avail})
        tmp = tmp[tmp["k"] != "NaT"]
        grouped = tmp.groupby("k")["a"]
        for key, group in grouped:
            non_null = group.dropna().drop_duplicates()
            if len(non_null) == 0:
                avail_map[str(key)] = None
            elif len(non_null) == 1:
                avail_map[str(key)] = non_null.iloc[0].date().isoformat()
            elif availability_policy == "earliest_available":
                avail_map[str(key)] = non_null.min().date().isoformat()
            elif availability_policy == "latest_available":
                avail_map[str(key)] = non_null.max().date().isoformat()
            else:
                raise ValueError(
                    "Multiple availability vintages exist for observation "
                    f"key {str(key)!r}; explicit availability_policy is "
                    "required ('earliest_available' or 'latest_available'), "
                    "or pass an already-vintage-filtered availability "
                    "mapping via AssetRequirement."
                )
    return AssetRequirement(
        asset_id=asset_id,
        venue=req_venue(venue),
        observation_dates=frozenset(keys),
        availability_by_date=avail_map,
        allow_pre_observation=allow_pre_observation,
        requires_calendar=requires_calendar,
    )


def req_venue(venue: str) -> str:
    if not venue:
        raise ValueError("AssetRequirement requires an explicit venue.")
    return venue


def summarize_exclusions(result: IntersectionResult) -> Dict[str, int]:
    summary: Dict[str, int] = {code: 0 for code in REASON_CODES}
    for item in result.excluded:
        summary[item.reason_code] = summary.get(item.reason_code, 0) + 1
    return summary
