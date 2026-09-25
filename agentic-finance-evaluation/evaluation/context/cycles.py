"""E4-F accumulation cycles (orchestration helpers; E4-owned).

Cycle structure:

* Cycle 1: frozen E4-E pipeline for M1 on W1 → locked C1.
* Cycle 2: R branch (C0 agent on W2) solely sources K2 evidence;
  P branch (C1 agent on W2) reads retention only; K2 passes the full
  extract → adjudicate → admit chain into the C1-seeded store → C2;
  terminal reads on W3 compare C0 / T12 / C1 / C1+C2.

Everything here is pure except the episode-executing drivers, which
live outside this module and call the frozen ``run_e4e`` per cycle.
No frozen code is modified; retrieval stays exact-match; the deliver()
cross-agent backstop is untouched.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.context.experiment import paired_delta
from evaluation.contracts.fingerprints import fingerprint_of_dict

CYCLES_METHOD = "e4f-accumulation-cycles"
CYCLES_VERSION = "v1"

DUAL_TEMPORARY_PROVENANCE = "temporary-no-store-dual"


def build_dual_temporary_payload(
    first_entries: Any, second_entries: Any
) -> Dict[str, Any]:
    """Build an explicitly provisional dual-instruction payload (T12).

    Contents mirror two admitted knowledge entries; lineage is
    temporary-only: no store, no verdicts, no mem-* identifiers, no
    persistence beyond the episode. Raises fail-closed on malformed
    or store-lineage-carrying entries via the single-entry builder.
    """
    from evaluation.context.experiment import _checked_entries

    first = _checked_entries(first_entries)
    second = _checked_entries(second_entries)
    if not first or not second:
        raise ValueError(
            "dual temporary context requires non-empty entries "
            "from both mechanisms: refusing partial instruction"
        )
    return {
        "entries": [dict(entry) for entry in (*first, *second)],
        "provisional": True,
        "provenance": DUAL_TEMPORARY_PROVENANCE,
    }


def apply_dual_temporary(agent: Any, payload: Mapping[str, Any]) -> Any:
    """Deliver a dual temporary payload to an isolated copy (T12 arm)."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    if payload.get("provisional") is not True:
        raise ValueError(
            "dual temporary delivery requires provisional=True: refusing"
        )
    if payload.get("provenance") != DUAL_TEMPORARY_PROVENANCE:
        raise ValueError(
            "dual temporary delivery requires provenance "
            f"{DUAL_TEMPORARY_PROVENANCE!r}: refusing foreign payloads"
        )
    from evaluation.context.experiment import _checked_entries

    _checked_entries(payload.get("entries", ()))
    if not callable(getattr(agent, "adapt", None)):
        raise TypeError("agent must expose a callable adapt()")
    if not callable(getattr(agent, "reset", None)):
        raise TypeError("agent must expose a callable reset()")
    isolated = copy.deepcopy(agent)
    from evaluation.contracts.fingerprints import thaw

    delivery = dict(payload)
    delivery["entries"] = [
        thaw(dict(entry)) for entry in delivery["entries"]
    ]
    isolated.adapt(delivery)
    return isolated


def retention_proof(store: Any) -> Dict[str, str]:
    """Map admitted context_id -> context fingerprint for one store.

    Byte-identity across cycles is proven by equality of this mapping
    (plus the store fingerprint) before and after Cycle 2.
    """
    from evaluation.context.memory import MemoryStore

    if not isinstance(store, MemoryStore):
        raise TypeError(
            f"store must be a MemoryStore, got {type(store).__name__}"
        )
    return {
        entry.context.context_id: entry.context.fingerprint()
        for entry in store.entries
    }


def assert_retained(
    before: Mapping[str, str], after: Mapping[str, str]
) -> Dict[str, str]:
    """Prove every pre-cycle entry survives byte-identical post-cycle."""
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise TypeError("retention maps must be mappings")
    missing = [key for key in before if key not in after]
    if missing:
        raise ValueError(
            f"retention failed, lost entries: {sorted(missing)}"
        )
    altered = sorted(
        key for key in before if after.get(key) != before[key]
    )
    if altered:
        raise ValueError(
            f"retention failed, altered entries: {altered}"
        )
    return dict(after)


def accumulation_delta(
    metrics_c0: Mapping[str, Optional[float]],
    metrics_dual_temp: Mapping[str, Optional[float]],
    metrics_accumulated: Mapping[str, Optional[float]],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Decisive contrasts: accumulated vs C0 and vs dual-temporary."""
    for name, mapping in (
        ("metrics_c0", metrics_c0),
        ("metrics_dual_temp", metrics_dual_temp),
        ("metrics_accumulated", metrics_accumulated),
    ):
        if not isinstance(mapping, Mapping):
            raise TypeError(f"{name} must be a mapping")
    return {
        "accumulated_vs_C0": paired_delta(
            metrics_c0, metrics_accumulated
        ),
        "accumulated_vs_dual_temp": paired_delta(
            metrics_dual_temp, metrics_accumulated
        ),
        "dual_temp_vs_C0": paired_delta(metrics_c0, metrics_dual_temp),
    }


@dataclass(frozen=True)
class E4FCycleResult:
    """Fingerprinted record of one E4-F accumulation campaign."""

    experiment_id: str
    execution_role: str
    execution_instance: str
    protocol_fingerprint: str
    windows: Mapping[str, Any]
    cycle_1: Mapping[str, Any]
    cycle_2: Mapping[str, Any]
    terminal: Mapping[str, Any]
    lineage: Mapping[str, Any]
    leakage: Mapping[str, Any]
    method: str = CYCLES_METHOD
    method_version: str = CYCLES_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "experiment_id",
            "execution_role",
            "execution_instance",
            "protocol_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for field_name in (
            "windows",
            "cycle_1",
            "cycle_2",
            "terminal",
            "lineage",
            "leakage",
        ):
            if not isinstance(getattr(self, field_name), Mapping):
                raise TypeError(f"{field_name} must be a mapping")
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        import json

        return {
            "experiment_id": self.experiment_id,
            "execution_role": self.execution_role,
            "execution_instance": self.execution_instance,
            "protocol_fingerprint": self.protocol_fingerprint,
            "windows": json.loads(json.dumps(dict(self.windows))),
            "cycle_1": json.loads(json.dumps(dict(self.cycle_1))),
            "cycle_2": json.loads(json.dumps(dict(self.cycle_2))),
            "terminal": json.loads(json.dumps(dict(self.terminal))),
            "lineage": dict(self.lineage),
            "leakage": dict(self.leakage),
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "E4FCycleResult":
        if not isinstance(payload, Mapping):
            raise TypeError("E4FCycleResult payload must be a mapping")
        known = {
            "experiment_id",
            "execution_role",
            "execution_instance",
            "protocol_fingerprint",
            "windows",
            "cycle_1",
            "cycle_2",
            "terminal",
            "lineage",
            "leakage",
            "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown E4FCycleResult fields: {sorted(extra)}"
            )
        try:
            return cls(
                experiment_id=payload["experiment_id"],
                execution_role=payload["execution_role"],
                execution_instance=payload["execution_instance"],
                protocol_fingerprint=payload["protocol_fingerprint"],
                windows=dict(payload["windows"]),
                cycle_1=dict(payload["cycle_1"]),
                cycle_2=dict(payload["cycle_2"]),
                terminal=dict(payload["terminal"]),
                lineage=dict(payload["lineage"]),
                leakage=dict(payload["leakage"]),
                method=payload.get("method", CYCLES_METHOD),
                method_version=payload.get("version", CYCLES_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"E4FCycleResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


__all__ = [
    "CYCLES_METHOD",
    "CYCLES_VERSION",
    "DUAL_TEMPORARY_PROVENANCE",
    "E4FCycleResult",
    "accumulation_delta",
    "apply_dual_temporary",
    "assert_retained",
    "build_dual_temporary_payload",
    "retention_proof",
]
