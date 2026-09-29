"""Append-only repair audit chain (M-R1, additive).

Hash-chained JSONL event log connecting diagnostic mechanism through
deactivation. Deterministic: ordering is the logical ``seq`` plus the
``prev_hash`` chain — no wall-clock timestamps. Uses the repository's
existing canonicalisation via RepairAuditRecord. Persists beside the
frozen manifest pattern (JSON, sorted keys).
"""

from __future__ import annotations

import json
import os
from typing import Any, List, Mapping, Sequence

from evaluation.repair.schemas import RepairAuditRecord

GENESIS_HASH = "GENESIS"


class AuditChain:
    """In-memory builder for a hash-chained audit log."""

    def __init__(self) -> None:
        self._records: List[RepairAuditRecord] = []

    def append(self, event: str, payload: Mapping[str, Any]) -> RepairAuditRecord:
        prev = (
            self._records[-1].event_hash() if self._records else GENESIS_HASH
        )
        record = RepairAuditRecord(
            seq=len(self._records) + 1,
            prev_hash=prev,
            event=event,
            payload=dict(payload),
        )
        self._records.append(record)
        return record

    def verify(self) -> bool:
        """Recompute the full chain; False on any break or resequencing."""
        prev = GENESIS_HASH
        for index, record in enumerate(self._records, start=1):
            if record.seq != index or record.prev_hash != prev:
                return False
            prev = record.event_hash()
        return True

    def to_list(self) -> List[dict]:
        return [record.to_dict() for record in self._records]

    @classmethod
    def from_list(cls, payloads: Sequence[Mapping[str, Any]]) -> "AuditChain":
        chain = cls()
        for payload in payloads:
            record = RepairAuditRecord(
                seq=payload["seq"],
                prev_hash=payload["prev_hash"],
                event=payload["event"],
                payload=dict(payload.get("payload", {})),
            )
            chain._records.append(record)
        if not chain.verify():
            raise ValueError("audit chain broken on load: refusing")
        return chain


def write_audit_log(path: str, chain: AuditChain) -> str:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(chain.to_list(), handle, sort_keys=True,
                  separators=(",", ":"))
        handle.write("\n")
    return path


def read_audit_log(path: str) -> AuditChain:
    with open(path, encoding="utf-8") as handle:
        payloads = json.load(handle)
    if not isinstance(payloads, list):
        raise ValueError("audit log must be a list of records")
    return AuditChain.from_list(payloads)


def audit_log_path(base_dir: str, basename: str) -> str:
    return os.path.join(base_dir, basename)
