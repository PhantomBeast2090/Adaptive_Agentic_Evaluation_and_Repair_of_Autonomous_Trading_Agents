"""Deterministic context assembly and isolated delivery (E4-D).

``assemble`` builds a fingerprinted ``ContextPackage`` from retrieved
contexts without reducing memory to an unstructured dump: mechanism,
pattern, triggering conditions, corrective principle, applicability,
contraindications, expected effect, validation evidence, provenance,
and version travel with every entry.

``deliver`` is the sole production caller of an agent's ``adapt()``:
it validates package/agent identity agreement, deep-copies the
agent, invokes ``adapt()`` exactly once on the copy with the
package payload, and returns the adapted copy plus a ``DeliveryRecord``
binding agent-before/agent-after/package fingerprints. The original
agent and the memory store are never mutated.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.retrieval import (
    RETRIEVAL_METHOD,
    RETRIEVAL_VERSION,
    RetrievalRecord,
)
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.fingerprints import (
    fingerprint_of_dict,
    freeze,
    thaw,
)

ASSEMBLY_METHOD = "context-assemble"
ASSEMBLY_VERSION = "v1"
DELIVERY_METHOD = "context-deliver"
DELIVERY_VERSION = "v1"


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ContextPackage:
    """One deterministic, fingerprintable delivery payload."""

    agent_identity: AgentIdentity
    store_fingerprint: str
    retrieved_ids: Tuple[str, ...] = ()
    knowledge: Tuple[Mapping[str, Any], ...] = ()  # type: ignore[assignment]
    retrieval_method: str = RETRIEVAL_METHOD
    retrieval_version: str = RETRIEVAL_VERSION
    method: str = ASSEMBLY_METHOD
    method_version: str = ASSEMBLY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.agent_identity, AgentIdentity):
            raise TypeError("agent_identity must be an AgentIdentity")
        _require_str(self.store_fingerprint, "store_fingerprint")
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
        knowledge = self.knowledge
        if isinstance(knowledge, str) or not isinstance(
            knowledge, (tuple, list)
        ):
            raise TypeError("knowledge must be a tuple/list of mappings")
        frozen = []
        for entry in knowledge:
            if not isinstance(entry, Mapping):
                raise TypeError("knowledge entries must be mappings")
            frozen.append(freeze(dict(entry)))
        object.__setattr__(self, "knowledge", tuple(frozen))
        for field_name in (
            "retrieval_method",
            "retrieval_version",
            "method",
            "method_version",
        ):
            _require_str(getattr(self, field_name), field_name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_identity": self.agent_identity.to_dict(),
            "store_fingerprint": self.store_fingerprint,
            "retrieved_ids": list(self.retrieved_ids),
            "knowledge": [thaw(entry) for entry in self.knowledge],
            "retrieval_method": self.retrieval_method,
            "retrieval_version": self.retrieval_version,
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextPackage":
        if not isinstance(payload, Mapping):
            raise TypeError("ContextPackage payload must be a mapping")
        known = {
            "agent_identity",
            "store_fingerprint",
            "retrieved_ids",
            "knowledge",
            "retrieval_method",
            "retrieval_version",
            "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown ContextPackage fields: {sorted(extra)}"
            )
        try:
            return cls(
                agent_identity=AgentIdentity.from_dict(
                    payload["agent_identity"]
                ),
                store_fingerprint=payload["store_fingerprint"],
                retrieved_ids=tuple(payload.get("retrieved_ids", ())),
                knowledge=tuple(payload.get("knowledge", ())),
                retrieval_method=payload.get(
                    "retrieval_method", RETRIEVAL_METHOD
                ),
                retrieval_version=payload.get(
                    "retrieval_version", RETRIEVAL_VERSION
                ),
                method=payload.get("method", ASSEMBLY_METHOD),
                method_version=payload.get("version", ASSEMBLY_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"ContextPackage payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class DeliveryRecord:
    """Provenance for one isolated context delivery."""

    agent_fingerprint_before: str
    agent_fingerprint_after: str
    context_package_fingerprint: str
    method: str = DELIVERY_METHOD
    method_version: str = DELIVERY_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "agent_fingerprint_before",
            "agent_fingerprint_after",
            "context_package_fingerprint",
            "method",
            "method_version",
        ):
            _require_str(getattr(self, field_name), field_name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_fingerprint_before": self.agent_fingerprint_before,
            "agent_fingerprint_after": self.agent_fingerprint_after,
            "context_package_fingerprint": (
                self.context_package_fingerprint
            ),
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeliveryRecord":
        if not isinstance(payload, Mapping):
            raise TypeError("DeliveryRecord payload must be a mapping")
        known = {
            "agent_fingerprint_before",
            "agent_fingerprint_after",
            "context_package_fingerprint",
            "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DeliveryRecord fields: {sorted(extra)}"
            )
        try:
            return cls(
                agent_fingerprint_before=payload[
                    "agent_fingerprint_before"
                ],
                agent_fingerprint_after=payload["agent_fingerprint_after"],
                context_package_fingerprint=payload[
                    "context_package_fingerprint"
                ],
                method=payload.get("method", DELIVERY_METHOD),
                method_version=payload.get("version", DELIVERY_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"DeliveryRecord payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def assemble(
    contexts: Tuple[LearnedContext, ...],
    record: RetrievalRecord,
    store_fingerprint: str,
    agent_identity: AgentIdentity,
) -> ContextPackage:
    """Build a ContextPackage from retrieved contexts (pure)."""
    if isinstance(contexts, str) or not isinstance(contexts, (tuple, list)):
        raise TypeError("contexts must be a tuple/list")
    contexts = tuple(contexts)
    if not isinstance(record, RetrievalRecord):
        raise TypeError(
            f"record must be a RetrievalRecord, "
            f"got {type(record).__name__}"
        )
    if not isinstance(agent_identity, AgentIdentity):
        raise TypeError("agent_identity must be an AgentIdentity")
    retrieved = [context.context_id for context in contexts]
    for context in contexts:
        if not isinstance(context, LearnedContext):
            raise TypeError(
                "contexts must contain LearnedContext, "
                f"got {type(context).__name__}"
            )
        if context.status is not ContextStatus.ADMITTED:
            raise ValueError(
                "assembly serves ADMITTED knowledge only; "
                f"{context.context_id!r} has status "
                f"{context.status.value}"
            )
    if sorted(retrieved) != sorted(record.retrieved_ids):
        raise ValueError(
            "assembled contexts must match the retrieval record exactly"
        )
    knowledge = tuple(
        {
            "context_id": context.context_id,
            "failure_mechanism": context.failure_mechanism,
            "observed_pattern": context.observed_pattern,
            "triggering_conditions": list(
                context.triggering_conditions
            ),
            "corrective_principle": context.corrective_principle,
            "applicability_conditions": list(
                context.applicability_conditions
            ),
            "contraindications": list(context.contraindications),
            "expected_effect": context.expected_effect,
            "validation_result": context.validation_result,
            "validation_metrics": dict(context.validation_metrics),
            "context_fingerprint": context.fingerprint(),
            "version": context.version,
        }
        for context in contexts
    )
    return ContextPackage(
        agent_identity=agent_identity,
        store_fingerprint=store_fingerprint,
        retrieved_ids=tuple(record.retrieved_ids),
        knowledge=knowledge,
        retrieval_method=record.method,
        retrieval_version=record.method_version,
    )


def deliver(
    agent: Any, package: ContextPackage
) -> Tuple[Any, DeliveryRecord]:
    """Deliver a ContextPackage to an isolated agent copy.

    Validates package/agent identity agreement, deep-copies the
    agent, invokes ``adapt()`` exactly once on the copy, and returns
    ``(adapted_copy, delivery_record)``. The original agent is never
    mutated. This is the sole production caller of ``adapt()``.
    """
    if not isinstance(package, ContextPackage):
        raise TypeError(
            f"package must be a ContextPackage, "
            f"got {type(package).__name__}"
        )
    identity = getattr(agent, "identity", None)
    if not isinstance(identity, AgentIdentity):
        raise TypeError("agent must expose an AgentIdentity")
    if (
        identity.agent_id != package.agent_identity.agent_id
        or identity.version != package.agent_identity.version
    ):
        raise ValueError(
            "package agent identity does not match the target agent: "
            "refusing cross-agent delivery"
        )
    if not callable(getattr(agent, "adapt", None)):
        raise TypeError("agent must expose a callable adapt()")
    if not callable(getattr(agent, "reset", None)):
        raise TypeError("agent must expose a callable reset()")
    from evaluation.diagnostics.repair.application import fingerprint_agent

    before = fingerprint_agent(agent, identity)
    isolated = copy.deepcopy(agent)
    # Deep-thaw: package knowledge is frozen (recursive tuples and
    # mapping proxies); the agent's mutable policy state must hold
    # only ordinary containers so fingerprint snapshotting keeps
    # working after delivery.
    isolated.adapt(
        {
            "context_package_fingerprint": package.fingerprint(),
            "entries": [thaw(dict(entry)) for entry in package.knowledge],
        }
    )
    after = fingerprint_agent(
        isolated, getattr(isolated, "identity")
    )
    return isolated, DeliveryRecord(
        agent_fingerprint_before=before,
        agent_fingerprint_after=after,
        context_package_fingerprint=package.fingerprint(),
    )
