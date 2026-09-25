"""Repair application with copy-on-write isolation (E2-F).

``apply_repair`` turns a ``RepairProposal`` plus the live original agent
into a repaired candidate without ever mutating the original:

1. validate the proposal and the agent (fail-closed, before touching
   anything);
2. verify the proposal's ``target_agent_fingerprint`` still matches the
   live agent (a proposal for one agent state cannot be applied to
   another);
3. ``copy.deepcopy`` the original (rollback = discard the copy);
4. wrap the copy in a ``GuardrailedAgent`` enforcing the proposal's
   declarative rules;
5. fingerprint both ends and return the frozen records plus the live
   candidate object for validation.

The candidate exposes the ``TargetAgent`` surface (``identity``,
``reset``, ``act``) and deliberately exposes no ``adapt``: candidates
are non-adaptive during validation. Rule semantics:

* ``per_session_order_cap {max_orders}`` — truncate the wrapped agent's
  order list to the first ``max_orders`` entries per decision;
* ``hold_all {}`` — suppress all orders (explicit inactivity switch,
  present so validation can prove that permanent inactivity is not
  automatically successful).

Unknown rule types fail the application loudly instead of degrading
into an undeclared no-op.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from evaluation.contracts.agent import AgentIdentity, validate_target_agent
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from evaluation.diagnostics.repair.proposal import RepairProposal


class ApplicationStatus(str, Enum):
    """Closed vocabulary for repair-application outcomes."""

    APPLIED = "APPLIED"
    FAILED = "FAILED"

    def to_str(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, value: object) -> "ApplicationStatus":
        for member in cls:
            if value == member.value:
                return member
        known = sorted(member.value for member in cls)
        raise ValueError(
            f"unknown ApplicationStatus {value!r}; known: {known}"
        )


def snapshot_policy(agent: Any) -> Mapping[str, Any]:
    """Capture a fingerprintable snapshot of an agent's mutable policy.

    Generic over current agent families: class identity plus a deep copy
    of instance state. Raises ``TypeError`` with an explicit reason when
    the state is not fingerprintable, instead of hashing something
    meaningless.
    """
    if agent is None:
        raise TypeError("cannot snapshot policy of None")
    try:
        state = copy.deepcopy(vars(agent))
    except (TypeError, AttributeError) as exc:
        raise TypeError(
            f"agent of type {type(agent).__name__} has no snapshottable "
            f"instance state: {exc}"
        ) from exc
    snapshot = {"class": type(agent).__name__, "state": state}
    try:
        fingerprint_of_dict(snapshot)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"agent policy state is not canonically fingerprintable: {exc}"
        ) from exc
    return snapshot


def fingerprint_agent(agent: Any, identity: AgentIdentity) -> str:
    """Deterministic identity over agent identity plus policy snapshot."""
    if not isinstance(identity, AgentIdentity):
        raise TypeError("identity must be an AgentIdentity")
    return fingerprint_of_dict(
        {"identity": identity.to_dict(), "policy": snapshot_policy(agent)}
    )


class GuardrailedAgent:
    """A repaired candidate: deepcopy of the original plus guardrails.

    The wrapped copy is owned exclusively by this object; the original
    agent is never referenced, so no mutation can leak back. Rule
    enforcement is declarative and recorded on the proposal.
    """

    def __init__(
        self,
        wrapped: Any,
        rules: Sequence[Mapping[str, Any]],
        candidate_identity: AgentIdentity,
    ) -> None:
        errors = validate_target_agent(wrapped)
        if errors:
            raise TypeError(f"wrapped agent is invalid: {errors}")
        if isinstance(rules, Mapping) or isinstance(rules, str):
            raise TypeError("rules must be a sequence of rule mappings")
        checked = []
        for rule in rules:
            if not isinstance(rule, Mapping):
                raise TypeError(
                    f"each rule must be a mapping, got {type(rule).__name__}"
                )
            kind = rule.get("type")
            if kind == "per_session_order_cap":
                cap = rule.get("max_orders")
                if (
                    not isinstance(cap, int)
                    or isinstance(cap, bool)
                    or cap < 0
                ):
                    raise ValueError(
                        "per_session_order_cap requires non-negative "
                        f"integer max_orders, got {cap!r}"
                    )
            elif kind == "hold_all":
                pass
            elif kind == "exposure_cap":
                breadth = rule.get("max_names_held")
                if (
                    not isinstance(breadth, int)
                    or isinstance(breadth, bool)
                    or breadth < 1
                ):
                    raise ValueError(
                        "exposure_cap requires positive integer "
                        f"max_names_held, got {breadth!r}"
                    )
            else:
                raise ValueError(
                    f"unsupported guardrail rule type {kind!r}: refusing "
                    "to degrade into an undeclared no-op"
                )
            checked.append(dict(rule))
        if not isinstance(candidate_identity, AgentIdentity):
            raise TypeError("candidate_identity must be an AgentIdentity")
        self._wrapped = wrapped
        self._rules = tuple(checked)
        self._identity = candidate_identity

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def rules(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(dict(rule) for rule in self._rules)

    def reset(self) -> None:
        self._wrapped.reset()

    def act(self, observation: Any) -> Sequence[Mapping[str, Any]]:
        orders = list(self._wrapped.act(observation))
        for rule in self._rules:
            if rule["type"] == "hold_all":
                return []
            if rule["type"] == "per_session_order_cap":
                orders = orders[: rule["max_orders"]]
            if rule["type"] == "exposure_cap":
                orders = self._apply_exposure_cap(orders, observation, rule)
        return orders

    @staticmethod
    def _apply_exposure_cap(
        orders: Sequence[Mapping[str, Any]],
        observation: Any,
        rule: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        """Drop BUYs that would broaden beyond max held names (breadth).

        Breadth (distinct held names) is read defensively from the
        observation portfolio; unreadable state degrades to an empty
        holding set, which admits new-name BUYs rather than
        suppressing them. SELLs and held-name orders always pass.
        """
        try:
            payload = (
                observation.to_dict()
                if hasattr(observation, "to_dict")
                else dict(observation)
            )
            positions = dict(
                payload.get("portfolio", {}).get("positions", {})
            )
        except (TypeError, ValueError, AttributeError):
            positions = {}
        held = set()
        for key, block in positions.items():
            try:
                quantity = float(dict(block).get("quantity", 0.0))
            except (TypeError, ValueError):
                continue
            if quantity > 0:
                held.add(str(key))
        cap = rule.get("max_names_held", 1)
        kept = []
        seen_new = set()
        for order in orders:
            if not isinstance(order, Mapping) or order.get("side") != "BUY":
                kept.append(order)
                continue
            key = f"{order.get('asset_id')}:{order.get('instrument')}"
            if key in held or key in seen_new:
                kept.append(order)
                continue
            if len(held | seen_new) >= cap:
                continue
            seen_new.add(key)
            kept.append(order)
        return kept


@dataclass(frozen=True)
class RepairedCandidate:
    """Frozen record for one repaired candidate (no live objects)."""

    candidate_id: str
    candidate_identity: AgentIdentity
    parent_identity: AgentIdentity
    parent_fingerprint: str
    candidate_fingerprint: str
    provider: str
    method: str
    method_version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    status: ApplicationStatus = ApplicationStatus.APPLIED
    error: Optional[str] = None

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_id",
            "parent_fingerprint",
            "candidate_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for field_name, kind in (
            ("candidate_identity", AgentIdentity),
            ("parent_identity", AgentIdentity),
        ):
            if not isinstance(getattr(self, field_name), kind):
                raise TypeError(
                    f"{field_name} must be an AgentIdentity"
                )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        object.__setattr__(
            self, "parameters", freeze(dict(self.parameters))
        )
        status = self.status
        if isinstance(status, str) and not isinstance(
            status, ApplicationStatus
        ):
            status = ApplicationStatus.from_str(status)
        if not isinstance(status, ApplicationStatus):
            raise TypeError(
                "status must be an ApplicationStatus member, "
                f"got {self.status!r}"
            )
        object.__setattr__(self, "status", status)
        if status is ApplicationStatus.APPLIED:
            if self.error is not None:
                raise ValueError(
                    "error must be None when status is APPLIED"
                )
        elif not isinstance(self.error, str) or not self.error.strip():
            raise ValueError(
                "error must be a non-empty string when status is FAILED"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_identity": self.candidate_identity.to_dict(),
            "parent_identity": self.parent_identity.to_dict(),
            "parent_fingerprint": self.parent_fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
            "provider": self.provider,
            "method": self.method,
            "method_version": self.method_version,
            "parameters": thaw(self.parameters),
            "status": self.status.value,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairedCandidate":
        if not isinstance(payload, Mapping):
            raise TypeError("RepairedCandidate payload must be a mapping")
        known = {
            "candidate_id", "candidate_identity", "parent_identity",
            "parent_fingerprint", "candidate_fingerprint", "provider",
            "method", "method_version", "parameters", "status", "error",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RepairedCandidate fields: {sorted(extra)}"
            )
        try:
            return cls(
                candidate_id=payload["candidate_id"],
                candidate_identity=AgentIdentity.from_dict(
                    payload["candidate_identity"]
                ),
                parent_identity=AgentIdentity.from_dict(
                    payload["parent_identity"]
                ),
                parent_fingerprint=payload["parent_fingerprint"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                provider=payload["provider"],
                method=payload["method"],
                method_version=payload["method_version"],
                parameters=dict(payload.get("parameters", {})),
                status=payload.get("status", "APPLIED"),
                error=payload.get("error"),
            )
        except KeyError as exc:
            raise ValueError(
                f"RepairedCandidate payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


@dataclass(frozen=True)
class RepairApplication:
    """Frozen record of one repair-application event."""

    application_id: str
    proposal_fingerprint: str
    pre_agent_fingerprint: str
    post_agent_fingerprint: str
    candidate_id: str
    status: ApplicationStatus = ApplicationStatus.APPLIED
    error: Optional[str] = None
    method: str = ""
    method_version: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "application_id",
            "proposal_fingerprint",
            "pre_agent_fingerprint",
            "post_agent_fingerprint",
            "candidate_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        status = self.status
        if isinstance(status, str) and not isinstance(
            status, ApplicationStatus
        ):
            status = ApplicationStatus.from_str(status)
        if not isinstance(status, ApplicationStatus):
            raise TypeError(
                "status must be an ApplicationStatus member, "
                f"got {self.status!r}"
            )
        object.__setattr__(self, "status", status)
        if status is ApplicationStatus.APPLIED:
            if self.error is not None:
                raise ValueError(
                    "error must be None when status is APPLIED"
                )
        elif not isinstance(self.error, str) or not self.error.strip():
            raise ValueError(
                "error must be a non-empty string when status is FAILED"
            )
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_id": self.application_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "pre_agent_fingerprint": self.pre_agent_fingerprint,
            "post_agent_fingerprint": self.post_agent_fingerprint,
            "candidate_id": self.candidate_id,
            "status": self.status.value,
            "error": self.error,
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairApplication":
        if not isinstance(payload, Mapping):
            raise TypeError("RepairApplication payload must be a mapping")
        known = {
            "application_id", "proposal_fingerprint",
            "pre_agent_fingerprint", "post_agent_fingerprint",
            "candidate_id", "status", "error", "method", "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown RepairApplication fields: {sorted(extra)}"
            )
        try:
            return cls(
                application_id=payload["application_id"],
                proposal_fingerprint=payload["proposal_fingerprint"],
                pre_agent_fingerprint=payload["pre_agent_fingerprint"],
                post_agent_fingerprint=payload["post_agent_fingerprint"],
                candidate_id=payload["candidate_id"],
                status=payload.get("status", "APPLIED"),
                error=payload.get("error"),
                method=payload["method"],
                method_version=payload.get("version", ""),
            )
        except KeyError as exc:
            raise ValueError(
                f"RepairApplication payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def _candidate_identity_for(
    parent_identity: AgentIdentity, proposal_fingerprint: str
) -> AgentIdentity:
    return AgentIdentity(
        agent_id=parent_identity.agent_id,
        version=f"{parent_identity.version}+r{proposal_fingerprint[:8]}",
    )


def apply_repair(
    proposal: RepairProposal, original_agent: Any, *, provider_name: str = ""
) -> Tuple[RepairedCandidate, RepairApplication, Any]:
    """Apply a proposal to a deep copy of the original agent.

    Returns ``(candidate_record, application_record, live_candidate)``.
    The original agent is never mutated; on any failure the copy is
    discarded and a FAILED application is still recorded explicitly.
    """
    if not isinstance(proposal, RepairProposal):
        raise TypeError(
            "proposal must be a RepairProposal, "
            f"got {type(proposal).__name__}"
        )
    errors = validate_target_agent(original_agent)
    if errors:
        raise TypeError(f"invalid target agent: {errors}")
    parent_identity = original_agent.identity
    if (
        parent_identity.agent_id != proposal.target_agent_identity.agent_id
        or parent_identity.version != proposal.target_agent_identity.version
    ):
        raise ValueError(
            "proposal targets a different agent identity than the supplied "
            "original agent"
        )
    try:
        live_pre_fp = fingerprint_agent(original_agent, parent_identity)
    except TypeError as exc:
        raise ValueError(
            f"original agent policy is not fingerprintable: {exc}"
        ) from exc
    if live_pre_fp != proposal.target_agent_fingerprint:
        raise ValueError(
            "proposal target fingerprint does not match the live original "
            "agent state: refusing to apply a stale proposal"
        )
    candidate_identity = _candidate_identity_for(
        parent_identity, proposal.fingerprint()
    )
    candidate_id = (
        f"{parent_identity.agent_id}@candidate-{proposal.fingerprint()[:8]}"
    )
    application_id = f"app-{proposal.fingerprint()[:16]}"
    try:
        owned_copy = copy.deepcopy(original_agent)
        rules = proposal.parameters.get("rules", [])
        candidate_agent: Any = GuardrailedAgent(
            owned_copy, rules, candidate_identity
        )
        post_fp = fingerprint_of_dict(
            {
                "identity": candidate_identity.to_dict(),
                "policy": snapshot_policy(owned_copy),
                "rules": [dict(rule) for rule in candidate_agent.rules],
            }
        )
    except Exception as exc:
        reason = (
            f"repair application failed and the copy was discarded: "
            f"{type(exc).__name__}: {exc}"
        )
        failed_candidate = RepairedCandidate(
            candidate_id=candidate_id,
            candidate_identity=candidate_identity,
            parent_identity=parent_identity,
            parent_fingerprint=live_pre_fp,
            candidate_fingerprint=live_pre_fp,
            provider=provider_name or proposal.method,
            method=proposal.method,
            method_version=proposal.method_version,
            parameters={"rules": []},
            status=ApplicationStatus.FAILED,
            error=reason,
        )
        failed_application = RepairApplication(
            application_id=application_id,
            proposal_fingerprint=proposal.fingerprint(),
            pre_agent_fingerprint=live_pre_fp,
            post_agent_fingerprint=live_pre_fp,
            candidate_id=candidate_id,
            status=ApplicationStatus.FAILED,
            error=reason,
            method=proposal.method,
            method_version=proposal.method_version,
        )
        return failed_candidate, failed_application, None
    candidate = RepairedCandidate(
        candidate_id=candidate_id,
        candidate_identity=candidate_identity,
        parent_identity=parent_identity,
        parent_fingerprint=live_pre_fp,
        candidate_fingerprint=post_fp,
        provider=provider_name or proposal.method,
        method=proposal.method,
        method_version=proposal.method_version,
        parameters={"rules": [dict(rule) for rule in candidate_agent.rules]},
        status=ApplicationStatus.APPLIED,
        error=None,
    )
    application = RepairApplication(
        application_id=application_id,
        proposal_fingerprint=proposal.fingerprint(),
        pre_agent_fingerprint=live_pre_fp,
        post_agent_fingerprint=post_fp,
        candidate_id=candidate_id,
        status=ApplicationStatus.APPLIED,
        error=None,
        method=proposal.method,
        method_version=proposal.method_version,
    )
    return candidate, application, candidate_agent
