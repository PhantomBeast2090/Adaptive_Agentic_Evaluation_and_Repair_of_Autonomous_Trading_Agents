"""Diagnostic episode configuration and artefact (E2-B).

``DiagnosticEpisodeConfig`` scopes one diagnostic episode: its window,
tradable universe, seed, and data root. It is validated fail-closed; the
universe shape is checked here while baseline-subset containment is
checked at materialisation time (which owns the baseline spec).

``DiagnosticEpisode`` is the minimal owner of one executed diagnostic
trajectory: the episode identity, the registered ``DiagnosticTestResult``,
and the episode's own ``DecisionRecord`` tuple. It exists because the
result alone carries only fingerprints — E2-C will need the records, and
they must live somewhere that is neither the frozen baseline artefact nor
mutable global state. Records may be empty only when execution never
produced a decision (``INVALID`` configuration, or failure before the
first step).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from evaluation.diagnostics.contracts.test_results import DiagnosticTestResult

UNIVERSE_ASSETS = ("nse_equity", "mcx_gold")


def _require_day(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a YYYY-MM-DD string")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be YYYY-MM-DD, got {value!r}"
        ) from exc
    return value


@dataclass(frozen=True)
class DiagnosticEpisodeConfig:
    """Explicit scope for one diagnostic episode."""

    start_date: str
    end_date: str
    universe: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    seed: int = 0
    base_dir: str = "."

    def __post_init__(self) -> None:
        start = _require_day(self.start_date, "start_date")
        end = _require_day(self.end_date, "end_date")
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)
        if start > end:
            raise ValueError(
                f"start_date {start} must not be after end_date {end}"
            )
        if not isinstance(self.universe, Mapping):
            raise TypeError("universe must be a mapping")
        unknown = set(self.universe) - set(UNIVERSE_ASSETS)
        if unknown:
            raise ValueError(f"unknown universe assets: {sorted(unknown)}")
        checked: Dict[str, Tuple[str, ...]] = {}
        total = 0
        for asset_id in UNIVERSE_ASSETS:
            instruments = self.universe.get(asset_id, ())
            if isinstance(instruments, str) or not isinstance(
                instruments, (tuple, list)
            ):
                raise TypeError(
                    f"universe[{asset_id!r}] must be a tuple/list of strings"
                )
            items = tuple(instruments)
            for item in items:
                if not isinstance(item, str) or not item:
                    raise ValueError(
                        f"universe[{asset_id!r}] entries must be non-empty "
                        "strings"
                    )
            if len(set(items)) != len(items):
                raise ValueError(
                    f"universe[{asset_id!r}] must not contain duplicates"
                )
            checked[asset_id] = items
            total += len(items)
        if total == 0:
            raise ValueError(
                "episode universe must name at least one instrument"
            )
        object.__setattr__(self, "universe", freeze(checked))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError(f"seed must be an int, got {self.seed!r}")
        if not isinstance(self.base_dir, str) or not self.base_dir:
            raise TypeError("base_dir must be a non-empty string")

    def identity_dict(self) -> Dict[str, Any]:
        """Identity-relevant scope (window, universe, seed).

        ``base_dir`` is provenance only and excluded, mirroring
        ``Trajectory.content_digest``: file identity travels with the
        market fingerprint, not the machine path.
        """
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "universe": {
                asset_id: sorted(instruments)
                for asset_id, instruments in thaw(self.universe).items()
            },
            "seed": self.seed,
        }

    def to_dict(self) -> Dict[str, Any]:
        payload = self.identity_dict()
        payload["base_dir"] = self.base_dir
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiagnosticEpisodeConfig":
        if not isinstance(payload, Mapping):
            raise TypeError("DiagnosticEpisodeConfig payload must be a mapping")
        known = {"start_date", "end_date", "universe", "seed", "base_dir"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DiagnosticEpisodeConfig fields: {sorted(extra)}"
            )
        try:
            return cls(
                start_date=payload["start_date"],
                end_date=payload["end_date"],
                universe=dict(payload.get("universe", {})),
                seed=payload.get("seed", 0),
                base_dir=payload.get("base_dir", "."),
            )
        except KeyError as exc:
            raise ValueError(
                f"DiagnosticEpisodeConfig payload missing {exc}"
            ) from exc


@dataclass(frozen=True)
class DiagnosticEpisode:
    """One executed diagnostic episode: result plus its own trajectory."""

    episode_id: str
    diagnostic_id: str
    test_id: str
    execution_fingerprint: str
    result: DiagnosticTestResult
    decision_records: Tuple[DecisionRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in (
            "episode_id",
            "diagnostic_id",
            "test_id",
            "execution_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.result, DiagnosticTestResult):
            raise TypeError(
                "result must be a DiagnosticTestResult, "
                f"got {type(self.result).__name__}"
            )
        records = self.decision_records
        if isinstance(records, str) or not isinstance(records, (tuple, list)):
            raise TypeError("decision_records must be a tuple/list")
        records = tuple(records)
        for record in records:
            if not isinstance(record, DecisionRecord):
                raise TypeError(
                    "decision_records must contain DecisionRecord, "
                    f"got {type(record).__name__}"
                )
        if [r.fingerprint() for r in records] != list(self.result.record_fps):
            raise ValueError(
                "episode decision records must match the result's record_fps "
                "in order"
            )
        object.__setattr__(self, "decision_records", records)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "diagnostic_id": self.diagnostic_id,
            "test_id": self.test_id,
            "execution_fingerprint": self.execution_fingerprint,
            "result": self.result.to_dict(),
            "decision_records": [r.to_dict() for r in self.decision_records],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiagnosticEpisode":
        if not isinstance(payload, Mapping):
            raise TypeError("DiagnosticEpisode payload must be a mapping")
        known = {
            "episode_id", "diagnostic_id", "test_id",
            "execution_fingerprint", "result", "decision_records",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DiagnosticEpisode fields: {sorted(extra)}"
            )
        try:
            return cls(
                episode_id=payload["episode_id"],
                diagnostic_id=payload["diagnostic_id"],
                test_id=payload["test_id"],
                execution_fingerprint=payload["execution_fingerprint"],
                result=DiagnosticTestResult.from_dict(payload["result"]),
                decision_records=tuple(
                    DecisionRecord.from_dict(item)
                    for item in payload.get("decision_records", ())
                ),
            )
        except KeyError as exc:
            raise ValueError(
                f"DiagnosticEpisode payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over episode, result, and trajectory."""
        return fingerprint_of_dict(self.to_dict())
