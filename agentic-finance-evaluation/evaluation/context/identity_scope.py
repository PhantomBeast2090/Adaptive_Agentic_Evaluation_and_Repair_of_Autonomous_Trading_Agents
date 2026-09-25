"""E4-E.1 identity-scope attestation (additive; E0–E4-D untouched).

A validated repair names its source agent (``proposal.target_agent_identity``,
folded into ``LearnedContext.agent_id`` by extraction), while E4 behavioural
delivery targets the context-enabled representation
(``contextual-threshold-benchmark@1.0``), which must live outside frozen
``benchmarks/``. Retrieval v1 matches exact ``agent_id`` strings, so the
scope bridge must be explicit, auditable, and fingerprinted — never fuzzy
matching, prefix matching, or an alias table.

``resolve_delivery_scope()`` binds, by machine-checkable proof:

* the repair source identity (parsed from the candidate, cross-checked
  against the live proposal identity object);
* the delivery identity (live ``AgentIdentity`` of the probe agent);
* the source base-policy fingerprint (fresh instance, pinned to the
  frozen manifest fingerprint);
* the delivery base-policy proof (frozen constants imported live,
  pinned to expected values; shared observation readers; adapt-surface
  asymmetry: source exposes no ``adapt``, delivery does);
* the knowledge lineage (candidate/admitted/verdict/store fingerprints).

It establishes execution-lineage scope sufficient for contextual delivery.
It does NOT establish behavioural equivalence, which stays empirical.

Fail-closed throughout: any mismatch raises; nothing is coerced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.fingerprints import fingerprint_of_dict

IDENTITY_SCOPE_METHOD = "identity-scope-attestation"
IDENTITY_SCOPE_VERSION = "v1"

# Closed v1 scope. Both ends are pinned: the only approved repair source
# is the frozen Class-B benchmark, and the only approved delivery
# representation is the E4 contextual benchmark. Widening the scope is a
# versioned change, never a silent one.
SOURCE_AGENT_ID = "volatility-threshold-benchmark"
SOURCE_AGENT_VERSION = "1.0"
DELIVERY_AGENT_ID = "contextual-threshold-benchmark"
DELIVERY_AGENT_VERSION = "1.0"

# E4-F accumulation scope (v2): the dual-guard delivery representation.
# Closed set: v1 admits only the single-guard benchmark; v2 additionally
# admits the accumulating benchmark. No other identity is ever approved.
APPROVED_DELIVERY_V2 = {
    "contextual-threshold-benchmark": "1.0",
    "accumulating-threshold-benchmark": "1.0",
}
IDENTITY_SCOPE_VERSION_V2 = "v2"

# Frozen manifest Class-B agent fingerprint (benchmarks/manifest.yaml,
# repairable Class-B row). Pinned here and cross-checked against the
# manifest file by test.
SOURCE_POLICY_FINGERPRINT = (
    "db16e4a862a4bb2a764fd7dc803a15a790457c847207db5b18fa41a3fe0a7f9c"
)

# Frozen Class-B policy constants (benchmarks/manifest.yaml
# class_b_constants + benchmarks/volatility_threshold.py). Asserted live
# against the imported code values; pinned against the manifest by test.
EXPECTED_BASE_CONSTANTS = {
    "VIX_LOW": 15.0,
    "VIX_HIGH": 25.0,
    "VIX_SLOT": "indiavix",
    "NSE_EQUITY_NAMES": ("RELIANCE:EQ", "TCS:EQ"),
    "BUILD_QUANTITY": 1.0,
    "REDUCE_QUANTITY": 5.0,
    "CASH_DUST": 1.0,
    "MAX_ORDERS_PER_SESSION": 3,
}

_BASE_CONSTANT_NAMES = tuple(EXPECTED_BASE_CONSTANTS)


@dataclass(frozen=True)
class IdentityScopeAttestation:
    """One explicit repair-source → delivery-target scope judgement."""

    source_agent_id: str
    source_version: str
    source_policy_fingerprint: str
    delivery_agent_id: str
    delivery_version: str
    wrapper_version: str
    base_policy_proof: Mapping[str, Any]
    context_id: str
    candidate_fingerprint: str
    admitted_fingerprint: str
    verdict_fingerprint: str
    store_fingerprint: str
    method: str = IDENTITY_SCOPE_METHOD
    method_version: str = IDENTITY_SCOPE_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "source_agent_id",
            "source_version",
            "source_policy_fingerprint",
            "delivery_agent_id",
            "delivery_version",
            "wrapper_version",
            "context_id",
            "candidate_fingerprint",
            "admitted_fingerprint",
            "verdict_fingerprint",
            "store_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.base_policy_proof, Mapping):
            raise TypeError("base_policy_proof must be a mapping")
        if set(self.base_policy_proof) != set(_BASE_CONSTANT_NAMES):
            raise ValueError(
                "base_policy_proof must carry exactly the frozen "
                f"constant names: {sorted(_BASE_CONSTANT_NAMES)}"
            )
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        proof = dict(self.base_policy_proof)
        proof["NSE_EQUITY_NAMES"] = list(proof["NSE_EQUITY_NAMES"])
        return {
            "source_agent_id": self.source_agent_id,
            "source_version": self.source_version,
            "source_policy_fingerprint": self.source_policy_fingerprint,
            "delivery_agent_id": self.delivery_agent_id,
            "delivery_version": self.delivery_version,
            "wrapper_version": self.wrapper_version,
            "base_policy_proof": proof,
            "context_id": self.context_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "admitted_fingerprint": self.admitted_fingerprint,
            "verdict_fingerprint": self.verdict_fingerprint,
            "store_fingerprint": self.store_fingerprint,
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> (
        "IdentityScopeAttestation"
    ):
        if not isinstance(payload, Mapping):
            raise TypeError(
                "IdentityScopeAttestation payload must be a mapping"
            )
        known = {
            "source_agent_id",
            "source_version",
            "source_policy_fingerprint",
            "delivery_agent_id",
            "delivery_version",
            "wrapper_version",
            "base_policy_proof",
            "context_id",
            "candidate_fingerprint",
            "admitted_fingerprint",
            "verdict_fingerprint",
            "store_fingerprint",
            "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown IdentityScopeAttestation fields: {sorted(extra)}"
            )
        try:
            proof = dict(payload["base_policy_proof"])
            proof["NSE_EQUITY_NAMES"] = tuple(proof["NSE_EQUITY_NAMES"])
            return cls(
                source_agent_id=payload["source_agent_id"],
                source_version=payload["source_version"],
                source_policy_fingerprint=payload[
                    "source_policy_fingerprint"
                ],
                delivery_agent_id=payload["delivery_agent_id"],
                delivery_version=payload["delivery_version"],
                wrapper_version=payload["wrapper_version"],
                base_policy_proof=proof,
                context_id=payload["context_id"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                admitted_fingerprint=payload["admitted_fingerprint"],
                verdict_fingerprint=payload["verdict_fingerprint"],
                store_fingerprint=payload["store_fingerprint"],
                method=payload.get("method", IDENTITY_SCOPE_METHOD),
                method_version=payload.get(
                    "version", IDENTITY_SCOPE_VERSION
                ),
            )
        except KeyError as exc:
            raise ValueError(
                f"IdentityScopeAttestation payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def _split_agent_string(value: Any) -> Tuple[str, str]:
    if not isinstance(value, str) or "@" not in value:
        raise ValueError(
            f"agent reference {value!r} is not an 'id@version' string: "
            "refusing to guess identity scope"
        )
    agent_id, _, version = value.rpartition("@")
    if not agent_id.strip() or not version.strip():
        raise ValueError(
            f"agent reference {value!r} has an empty id or version: "
            "refusing"
        )
    return agent_id, version


def resolve_delivery_scope(
    *,
    candidate: Any,
    proposal: Any,
    verdict: Any,
    store: Any,
    delivery_agent: Any,
    scope_version: str = "v1",
) -> Tuple[str, IdentityScopeAttestation]:
    """Attest repair-source → delivery-target scope; return scope string.

    Returns ``(retrieval_agent_id_str, attestation)`` where the string is
    the source ``agent_id`` carried by the candidate — the exact-match
    key ``retrieve()`` must be called with. Callers pass the delivery
    probe's own identity to ``assemble()`` and deliver normally, so
    retrieval exactness and the ``deliver()`` cross-agent backstop are
    untouched. Raises fail-closed on any mismatch.
    """
    from evaluation.context.learned import ContextStatus, LearnedContext
    from evaluation.context.memory import MemoryStore
    from evaluation.diagnostics.repair.application import fingerprint_agent

    for name, value, kind in (
        ("candidate", candidate, LearnedContext),
        ("store", store, MemoryStore),
    ):
        if not isinstance(value, kind):
            raise TypeError(
                f"{name} must be a {kind.__name__}, "
                f"got {type(value).__name__}"
            )
    if candidate.status is not ContextStatus.VALIDATED:
        raise ValueError(
            "scope is attested for gate-validated knowledge only; "
            f"got {candidate.status.value}"
        )

    # Source end: parsed from the candidate string, cross-checked
    # against the live proposal identity object (never trusted alone).
    source_id, source_version = _split_agent_string(candidate.agent_id)
    if (source_id, source_version) != (
        SOURCE_AGENT_ID,
        SOURCE_AGENT_VERSION,
    ):
        raise ValueError(
            f"repair source {candidate.agent_id!r} is outside the "
            f"approved v1 scope ({SOURCE_AGENT_ID}@{SOURCE_AGENT_VERSION}): "
            "refusing unattested scope"
        )
    target_identity = getattr(proposal, "target_agent_identity", None)
    if not isinstance(target_identity, AgentIdentity):
        raise TypeError(
            "proposal must carry an AgentIdentity target: refusing"
        )
    if (
        target_identity.agent_id != source_id
        or target_identity.version != source_version
    ):
        raise ValueError(
            "candidate source does not match the live proposal target "
            "identity: refusing cross-repair scope"
        )
    proposal_fp = getattr(proposal, "fingerprint", None)
    if not callable(proposal_fp):
        raise TypeError(
            "proposal must expose a fingerprint(): refusing"
        )
    recorded_proposal_fp = dict(candidate.provenance).get(
        "proposal_fingerprint", ""
    )
    if recorded_proposal_fp != proposal.fingerprint():
        raise ValueError(
            "candidate provenance does not reference this exact "
            "proposal: refusing cross-repair scope"
        )

    # Delivery end: approved representation, live identity, empty context.
    if scope_version not in ("v1", IDENTITY_SCOPE_VERSION_V2):
        raise ValueError(
            f"unsupported scope version {scope_version!r}: refusing"
        )
    approved = (
        {DELIVERY_AGENT_ID: DELIVERY_AGENT_VERSION}
        if scope_version == "v1"
        else dict(APPROVED_DELIVERY_V2)
    )
    delivery_identity = getattr(delivery_agent, "identity", None)
    if not isinstance(delivery_identity, AgentIdentity):
        raise TypeError("delivery agent must expose an AgentIdentity")
    if (
        approved.get(delivery_identity.agent_id)
        != delivery_identity.version
    ):
        raise ValueError(
            f"delivery agent {delivery_identity!r} is not an approved "
            f"{scope_version} representation: refusing"
        )
    if not callable(getattr(delivery_agent, "adapt", None)):
        raise TypeError("delivery agent must expose a callable adapt()")
    if not callable(getattr(delivery_agent, "reset", None)):
        raise TypeError("delivery agent must expose a callable reset()")
    if tuple(getattr(delivery_agent, "learned_contexts", ())) != ():
        raise ValueError(
            "scope is attested for a fresh delivery representation "
            "only: refusing an already-contextualised agent"
        )

    # Base-policy proof, machine-checked live.
    from benchmarks.volatility_threshold import (
        VolatilityThresholdBenchmark,
    )
    from evaluation.context.benchmark import ContextualThresholdBenchmark

    if getattr(VolatilityThresholdBenchmark, "adapt", None) is not None:
        raise ValueError(
            "source benchmark exposes an adapt surface: the v1 scope "
            "rationale no longer holds"
        )
    if not callable(getattr(ContextualThresholdBenchmark, "adapt", None)):
        raise ValueError(
            "delivery representation exposes no adapt surface: "
            "refusing"
        )
    import benchmarks.volatility_threshold as frozen_policy

    proof: Dict[str, Any] = {}
    for name in _BASE_CONSTANT_NAMES:
        value = getattr(frozen_policy, name, None)
        if value is None:
            raise ValueError(
                f"frozen policy lacks constant {name!r}: refusing"
            )
        proof[name] = value
    normalised = {
        key: (tuple(value) if isinstance(value, (tuple, list)) else value)
        for key, value in proof.items()
    }
    expected = {
        key: (tuple(value) if isinstance(value, (tuple, list)) else value)
        for key, value in EXPECTED_BASE_CONSTANTS.items()
    }
    if normalised != expected:
        raise ValueError(
            "frozen base-policy constants drifted from the approved "
            "v1 proof: refusing"
        )
    source_probe = VolatilityThresholdBenchmark()
    source_fp = fingerprint_agent(source_probe, source_probe.identity)
    if source_fp != SOURCE_POLICY_FINGERPRINT:
        raise ValueError(
            "source base-policy fingerprint does not match the frozen "
            "manifest fingerprint: refusing"
        )

    # Knowledge lineage from the live store (proves admission).
    candidate_fp = candidate.fingerprint()
    decision = getattr(
        getattr(verdict, "decision", None), "value",
        getattr(verdict, "decision", None),
    )
    if decision != "ADMITTED":
        raise ValueError(
            f"scope requires an ADMITTED verdict, got {decision!r}"
        )
    if getattr(verdict, "candidate_fingerprint", None) != candidate_fp:
        raise ValueError(
            "verdict does not describe this candidate: refusing"
        )
    match = [
        entry for entry in store.entries
        if entry.candidate_fingerprint == candidate_fp
    ]
    if len(match) != 1:
        raise ValueError(
            "candidate is not admitted exactly once in the live store: "
            "refusing"
        )
    admitted_fp = match[0].context.fingerprint()

    attestation = IdentityScopeAttestation(
        source_agent_id=source_id,
        source_version=source_version,
        source_policy_fingerprint=source_fp,
        delivery_agent_id=delivery_identity.agent_id,
        delivery_version=delivery_identity.version,
        wrapper_version=delivery_identity.version,
        method=IDENTITY_SCOPE_METHOD,
        method_version=(
            IDENTITY_SCOPE_VERSION_V2
            if scope_version == IDENTITY_SCOPE_VERSION_V2
            else IDENTITY_SCOPE_VERSION
        ),
        base_policy_proof={
            key: (tuple(value) if isinstance(value, tuple) else value)
            for key, value in proof.items()
        },
        context_id=candidate.context_id,
        candidate_fingerprint=candidate_fp,
        admitted_fingerprint=admitted_fp,
        verdict_fingerprint=verdict.fingerprint(),
        store_fingerprint=store.fingerprint(),
    )
    return candidate.agent_id, attestation
