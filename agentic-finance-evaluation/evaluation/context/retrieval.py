"""Deterministic structured retrieval, v1 (E4-D).

``retrieve`` selects admitted store entries by exact ``agent_id``
match, in deterministic sequence order. No embeddings, no similarity
search, no regime/asset ranking, no heuristic relevance scoring, no
randomness, no hidden state. Contraindications are preserved
downstream in the assembled package but do not gate v1 retrieval;
any future selective use is a versioned retrieval change, never a
silent one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from evaluation.context.learned import LearnedContext
from evaluation.context.memory import MemoryStore
from evaluation.contracts.fingerprints import fingerprint_of_dict

RETRIEVAL_METHOD = "context-retrieve"
RETRIEVAL_VERSION = "v1"


@dataclass(frozen=True)
class RetrievalRecord:
    """Provenance for one deterministic retrieval operation."""

    agent_id: str
    store_fingerprint: str
    retrieved_ids: Tuple[str, ...] = ()
    method: str = RETRIEVAL_METHOD
    method_version: str = RETRIEVAL_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        if (
            not isinstance(self.store_fingerprint, str)
            or not self.store_fingerprint.strip()
        ):
            raise ValueError("store_fingerprint must be a non-empty string")
        ids = self.retrieved_ids
        if isinstance(ids, str) or not isinstance(ids, (tuple, list)):
            raise TypeError("retrieved_ids must be a tuple/list of strings")
        ids = tuple(ids)
        for item in ids:
            if not isinstance(item, str) or not item:
                raise ValueError(
                    "retrieved_ids entries must be non-empty strings"
                )
        if len(set(ids)) != len(ids):
            raise ValueError("retrieved_ids must not contain duplicates")
        object.__setattr__(self, "retrieved_ids", ids)
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "store_fingerprint": self.store_fingerprint,
            "retrieved_ids": list(self.retrieved_ids),
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RetrievalRecord":
        if not isinstance(payload, Mapping):
            raise TypeError("RetrievalRecord payload must be a mapping")
        known = {
            "agent_id",
            "store_fingerprint",
            "retrieved_ids",
            "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RetrievalRecord fields: {sorted(extra)}"
            )
        try:
            return cls(
                agent_id=payload["agent_id"],
                store_fingerprint=payload["store_fingerprint"],
                retrieved_ids=tuple(payload.get("retrieved_ids", ())),
                method=payload.get("method", RETRIEVAL_METHOD),
                method_version=payload.get("version", RETRIEVAL_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"RetrievalRecord payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def retrieve(
    store: MemoryStore, *, agent_id: str
) -> Tuple[Tuple[LearnedContext, ...], RetrievalRecord]:
    """Return admitted entries for one agent plus the retrieval record.

    Exact ``agent_id`` match only, store sequence order. The store is
    never mutated; only ADMITTED entries can exist in it by
    construction, so retrieval cannot serve unadmitted knowledge.
    """
    if not isinstance(store, MemoryStore):
        raise TypeError(
            f"store must be a MemoryStore, got {type(store).__name__}"
        )
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agent_id must be a non-empty string")
    matched = tuple(
        entry.context
        for entry in store.entries
        if entry.context.agent_id == agent_id
    )
    record = RetrievalRecord(
        agent_id=agent_id,
        store_fingerprint=store.fingerprint(),
        retrieved_ids=tuple(context.context_id for context in matched),
    )
    return matched, record
