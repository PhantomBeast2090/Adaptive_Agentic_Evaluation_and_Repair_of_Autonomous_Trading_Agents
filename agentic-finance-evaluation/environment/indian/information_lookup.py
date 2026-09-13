"""Single explicit information-lookup bridge: canonical data -> environment.

Conceptually::

    get_information(asset_id, decision_timestamp, vintage_policy)

Every lookup returns a typed AssetSlot carrying observation, availability,
vintage, venue, eligibility, and reason. PIT logic is NOT duplicated here:
market/session assets reuse the observation-lag rule documented on their
AssetSpec, and vintage assets delegate to InformationSet.

Two paths (chosen by AssetSpec.lookup_path, never inferred):

- observation_lag: the visible row is the latest row whose observation key
  is strictly before the decision timestamp (date grain). Explicit
  assumption: publication lag of at least one day; no intraday timing is
  claimed. Same-date observations are NEVER visible, so same-bar closes
  cannot leak into decisions.
- vintage_pit: InformationSet latest-eligible-vintage semantics driven by
  the availability column. Rows with NULL availability are excluded BEFORE
  InformationSet construction (which would otherwise raise) and remain
  INFO_UNAVAILABLE. The caller's vintage_policy selects earliest/latest
  only through build_requirement_from_frame-compatible explicit choice;
  this module defaults to latest-eligible (InformationSet semantics) and
  never silently aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from environment.indian.asset_contract import AssetSpec
from environment.indian.registry import get_spec
from src.india.information_set import InformationSet

# Slot statuses reuse the experiment-intersection reason vocabulary, plus
# AVAILABLE for the eligible case.
STATUS_AVAILABLE = "AVAILABLE"
STATUS_OBS_MISSING = "OBS_MISSING"
STATUS_INFO_UNAVAILABLE = "INFO_UNAVAILABLE"
STATUS_CAL_UNKNOWN = "CAL_UNKNOWN"
STATUS_CAL_CLOSED = "CAL_CLOSED"
STATUS_CONSTRAINT_FAIL = "CONSTRAINT_FAIL"


@dataclass(frozen=True)
class AssetSlot:
    """One asset's resolved information state at a decision timestamp."""

    asset_id: str
    venue: str
    status: str
    decision_timestamp: str
    observation_date: Optional[str] = None
    availability_date: Optional[str] = None
    vintage: Optional[int] = None
    values: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class _SeriesCache:
    """Per-asset canonical frames, loaded once and sorted by observation key."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self._frames: Dict[str, pd.DataFrame] = {}

    def frame_for(self, spec: AssetSpec, id_filter: Optional[Dict[str, str]] = None) -> pd.DataFrame:
        key = spec.asset_id + "|" + repr(sorted((id_filter or {}).items()))
        if key not in self._frames:
            self._frames[key] = _load_series(spec, self.base_dir, id_filter)
        return self._frames[key]


def _load_series(spec: AssetSpec, base_dir: str,
                 id_filter: Optional[Dict[str, str]]) -> pd.DataFrame:
    import os
    path = os.path.join(base_dir, spec.csv_path)
    # NSE equities is ~1GB: read only needed columns.
    use = [spec.observation_col] + list(spec.price_fields) + list(spec.id_cols)
    if spec.availability_col:
        use.append(spec.availability_col)
    if spec.asset_id in ("cpi", "iip"):
        use += ["revision_version", "vintage_status"]
    if spec.asset_id == "rbi_policy":
        use += ["revision_version" if "revision_version" in
                pd.read_csv(path, nrows=0).columns else spec.observation_col]
    use = list(dict.fromkeys(u for u in use if u))
    frame = pd.read_csv(path, usecols=lambda c: c in set(use))
    if id_filter:
        for col, val in id_filter.items():
            frame = frame[frame[col].astype(str) == str(val)]
    frame = frame.copy()
    frame["_obs"] = pd.to_datetime(frame[spec.observation_col], errors="coerce")
    frame = frame.dropna(subset=["_obs"]).sort_values("_obs").reset_index(drop=True)
    return frame


class InformationLookup:
    """Resolve AssetSlots at caller-supplied decision timestamps."""

    def __init__(self, base_dir: str = ".", strict: bool = True):
        self.base_dir = base_dir
        self.strict = strict
        self._cache = _SeriesCache(base_dir)
        self._info_sets: Dict[str, InformationSet] = {}

    # -- public API ----------------------------------------------------

    def get_information(
        self,
        asset_id: str,
        decision_timestamp: object,
        vintage_policy: str = "explicit",
        id_filter: Optional[Dict[str, str]] = None,
    ) -> AssetSlot:
        spec = get_spec(asset_id)
        day = pd.to_datetime(decision_timestamp, errors="coerce", utc=True)
        if pd.isna(day):
            return AssetSlot(asset_id, spec.venue, STATUS_CONSTRAINT_FAIL,
                             str(decision_timestamp),
                             reason="Decision timestamp missing/unparseable.")
        stamp = day.date().isoformat()
        frame = self._cache.frame_for(spec, id_filter)
        if spec.lookup_path == "vintage_pit":
            return self._vintage_slot(spec, frame, stamp, vintage_policy)
        return self._lag_slot(spec, frame, stamp)

    # -- observation-lag path ------------------------------------------

    def _lag_slot(self, spec: AssetSpec, frame: pd.DataFrame, stamp: str) -> AssetSlot:
        decision_day = pd.Timestamp(stamp, tz="UTC")
        eligible = frame[frame["_obs"].dt.tz_localize("UTC") < decision_day]
        if eligible.empty:
            return AssetSlot(spec.asset_id, spec.venue, STATUS_OBS_MISSING, stamp,
                             reason="No observation strictly before decision timestamp.")
        row = eligible.iloc[-1]
        values = {}
        for col in spec.price_fields:
            if col in row and pd.notna(row[col]):
                values[col] = float(row[col])
        if not values:
            return AssetSlot(spec.asset_id, spec.venue, STATUS_OBS_MISSING, stamp,
                             observation_date=row["_obs"].date().isoformat(),
                             reason="Latest prior observation has no usable price/value.")
        avail = None
        if spec.availability_col and spec.availability_col in row and pd.notna(row[spec.availability_col]):
            avail = pd.to_datetime(row[spec.availability_col]).date().isoformat()
        return AssetSlot(
            asset_id=spec.asset_id, venue=spec.venue, status=STATUS_AVAILABLE,
            decision_timestamp=stamp,
            observation_date=row["_obs"].date().isoformat(),
            availability_date=avail,
            values=values,
            reason="Latest observation strictly before decision timestamp "
                   "(explicit >=1-day publication-lag assumption).",
        )

    # -- vintage PIT path ----------------------------------------------

    def _vintage_slot(self, spec: AssetSpec, frame: pd.DataFrame, stamp: str,
                      vintage_policy: str) -> AssetSlot:
        if vintage_policy not in ("explicit", "earliest_available", "latest_available"):
            return AssetSlot(spec.asset_id, spec.venue, STATUS_CONSTRAINT_FAIL, stamp,
                             reason=f"Unknown vintage_policy {vintage_policy!r}.")
        work = frame.copy()
        if spec.availability_col and spec.availability_col in work.columns:
            known = work[pd.to_datetime(work[spec.availability_col],
                                        errors="coerce", utc=True).notna()]
        else:
            known = work.iloc[0:0]
        if known.empty:
            return AssetSlot(spec.asset_id, spec.venue, STATUS_INFO_UNAVAILABLE, stamp,
                             reason="No vintage with known availability; strict PIT "
                                    "keeps the asset invisible.")
        adapted = known.rename(columns={spec.observation_col: "observation_date",
                                        spec.availability_col: "availability_date"})
        if "variable" not in adapted.columns:
            adapted = adapted.copy()
            adapted["variable"] = spec.asset_id
        if "revision_version" not in adapted.columns:
            adapted = adapted.copy()
            adapted["revision_version"] = 0
        key = spec.asset_id
        if key not in self._info_sets:
            self._info_sets[key] = InformationSet(
                adapted[["variable", "observation_date", "availability_date",
                         "revision_version"]],
                allow_pre_observation=spec.allow_pre_observation,
            )
        info = self._info_sets[key].information_available_at(stamp)
        if info.empty:
            return AssetSlot(spec.asset_id, spec.venue, STATUS_INFO_UNAVAILABLE, stamp,
                             reason="No vintage available at decision timestamp.")
        # Latest observation period wins; ties resolve per vintage_policy.
        latest_obs = info["observation_date"].max()
        cands = info[info["observation_date"] == latest_obs].sort_values("revision_version")
        if vintage_policy == "earliest_available":
            pick = cands.iloc[0]
        else:  # explicit / latest_available -> InformationSet latest eligible
            pick = cands.iloc[-1]
        obs_key = pd.to_datetime(pick["observation_date"]).date().isoformat()
        src = known[pd.to_datetime(known[spec.observation_col]).dt.date.astype(str) == obs_key]
        values = {}
        if not src.empty:
            row = src.iloc[-1]
            for col in spec.price_fields:
                if col in row and pd.notna(row[col]):
                    values[col] = float(row[col])
        return AssetSlot(
            asset_id=spec.asset_id, venue=spec.venue, status=STATUS_AVAILABLE,
            decision_timestamp=stamp, observation_date=obs_key,
            availability_date=pd.to_datetime(pick["_availability_timestamp"]).date().isoformat(),
            vintage=int(pick["revision_version"]), values=values,
            reason="Latest eligible vintage at decision timestamp "
                   "(InformationSet semantics).",
        )

    def bar_close(
        self,
        asset_id: str,
        id_filter: Optional[Dict[str, str]],
        observation_date: str,
    ) -> Optional[float]:
        """Exact-bar close for one instrument on one observation date.

        Returns None when the bar is absent or has no usable price. Used
        for execution prices and marks; never substitutes another date's
        price.
        """
        spec = get_spec(asset_id)
        frame = self._cache.frame_for(spec, id_filter)
        hits = frame[frame["_obs"].dt.date.astype(str) == observation_date]
        if hits.empty:
            return None
        row = hits.iloc[-1]
        for col in spec.price_fields:
            if col in row and pd.notna(row[col]) and float(row[col]) > 0:
                return float(row[col])
        return None

    def provenance(self, asset_id: str,
                   id_filter: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        spec = get_spec(asset_id)
        frame = self._cache.frame_for(spec, id_filter)
        out: Dict[str, Any] = {
            "asset_id": asset_id, "rows": len(frame),
            "lookup_path": spec.lookup_path,
        }
        if not frame.empty:
            out["first_observation"] = frame["_obs"].min().date().isoformat()
            out["last_observation"] = frame["_obs"].max().date().isoformat()
        if spec.availability_col and spec.availability_col in frame.columns:
            out["null_availability"] = int(
                pd.to_datetime(frame[spec.availability_col],
                               errors="coerce", utc=True).isna().sum())
        return out
