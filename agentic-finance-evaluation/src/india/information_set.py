"""Point-in-time information-set construction for Indian macro data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


class InformationSet:
    """Select only the latest vintage known at a simulation timestamp.

    Rows must contain ``variable``, ``observation_date``,
    ``availability_timestamp`` (or ``availability_date``), and
    ``revision_version``. A later revision is never visible before its own
    availability timestamp.
    """

    def __init__(
        self,
        vintages: pd.DataFrame,
        *,
        allow_pre_observation: bool = False,
    ) -> None:
        required = {
            "variable",
            "observation_date",
            "revision_version",
        }
        missing = sorted(required - set(vintages.columns))
        if missing:
            raise ValueError(f"Vintage data missing required columns: {missing}")
        self._vintages = vintages.copy()
        self._vintages["observation_date"] = pd.to_datetime(
            self._vintages["observation_date"], errors="raise"
        )
        availability_column = (
            "availability_timestamp"
            if "availability_timestamp" in self._vintages.columns
            else "availability_date"
            if "availability_date" in self._vintages.columns
            else None
        )
        if availability_column is None:
            raise ValueError(
                "Vintage data requires availability_timestamp or availability_date."
            )
        availability = pd.to_datetime(
            self._vintages[availability_column], errors="coerce", utc=True
        )
        if availability.isna().any():
            raise ValueError(
                "Every vintage must have a reliable availability timestamp; "
                "missing release timing is not experiment-eligible."
            )
        if not allow_pre_observation and (
            availability.dt.date
            < self._vintages["observation_date"].dt.date
        ).any():
            raise ValueError(
                "A retrospective vintage is available before its observation period."
            )
        self._vintages["_availability_timestamp"] = availability
        self._vintages["revision_version"] = pd.to_numeric(
            self._vintages["revision_version"], errors="raise"
        ).astype(int)

    def information_available_at(
        self,
        timestamp: date | datetime | pd.Timestamp,
        variable: str | None = None,
    ) -> pd.DataFrame:
        """Return the latest eligible vintage per variable/observation date."""
        point = pd.Timestamp(timestamp)
        if point.tzinfo is None:
            point = point.tz_localize("UTC")
        else:
            point = point.tz_convert("UTC")
        eligible = self._vintages[
            self._vintages["_availability_timestamp"] <= point
        ]
        if variable is not None:
            eligible = eligible[eligible["variable"] == variable]
        if eligible.empty:
            return eligible.copy()
        ordered = eligible.sort_values(
            [
                "variable",
                "observation_date",
                "_availability_timestamp",
                "revision_version",
            ]
        )
        return (
            ordered
            .drop_duplicates(["variable", "observation_date"], keep="last")
            .sort_values(["variable", "observation_date"])
            .reset_index(drop=True)
        )
