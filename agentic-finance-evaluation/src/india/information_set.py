"""Point-in-time information-set construction for Indian macro data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


class InformationSet:
    """Select only the latest vintage known at a simulation timestamp.

    Rows must contain ``variable``, ``observation_date``,
    ``availability_date``, and ``revision_version``.  A later revision is
    never visible before its own availability date.
    """

    def __init__(self, vintages: pd.DataFrame) -> None:
        required = {
            "variable",
            "observation_date",
            "availability_date",
            "revision_version",
        }
        missing = sorted(required - set(vintages.columns))
        if missing:
            raise ValueError(f"Vintage data missing required columns: {missing}")
        self._vintages = vintages.copy()
        self._vintages["observation_date"] = pd.to_datetime(
            self._vintages["observation_date"], errors="raise"
        )
        self._vintages["availability_date"] = pd.to_datetime(
            self._vintages["availability_date"], errors="raise"
        )
        if (self._vintages["availability_date"] < self._vintages["observation_date"]).any():
            raise ValueError("A retrospective vintage is available before its observation period.")
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
        eligible = self._vintages[self._vintages["availability_date"] <= point]
        if variable is not None:
            eligible = eligible[eligible["variable"] == variable]
        if eligible.empty:
            return eligible.copy()
        ordered = eligible.sort_values(
            ["variable", "observation_date", "availability_date", "revision_version"]
        )
        return (
            ordered
            .drop_duplicates(["variable", "observation_date"], keep="last")
            .sort_values(["variable", "observation_date"])
            .reset_index(drop=True)
        )
