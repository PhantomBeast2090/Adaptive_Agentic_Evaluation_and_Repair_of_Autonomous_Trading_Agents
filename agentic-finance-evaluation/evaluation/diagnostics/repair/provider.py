"""Repair provider boundary (E2-F).

A ``RepairProvider`` turns a diagnosed hypothesis into a
``RepairProposal``. The boundary is deliberately narrow: the provider
receives the hypothesis claim, its evidence references, the frozen
target-agent identity, and a policy snapshot function — never raw market
data, oracle packets, environment state, or the live agent object for
mutation. (The live object is passed to ``apply_repair`` separately, so
read access during proposal cannot become write access by accident.)

v1 ships exactly one deterministic implementation,
``DeterministicRuleProvider`` (method ``rule-table``, version ``v1``):
a versioned failure-class table mapping a diagnosed failure to an
explicit guardrail rule set plus a target metric and direction. The
table is blunt by design — validation, not provider cleverness, judges
whether the guardrail helped. An LLM or learned provider may implement
this Protocol later; it must then declare ``deterministic = False`` and
is excluded from determinism claims.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Protocol, Tuple

from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.contracts.predictions import ExpectedDirection
from evaluation.diagnostics.repair.proposal import RepairProposal

PROVIDER_METHOD = "rule-table"
PROVIDER_VERSION = "v1"

# Failure-class keyword -> (rules, target_metric, rationale fragment).
# Matching is case-insensitive substring on failure_class. The table is
# intentionally small: v1 guardrails throttle trading intensity, which
# directly addresses overtrading and plausibly limits position build-up
# behind risk-class failures. Anything unlisted falls through to the
# default guardrail rather than refusing: refusing would conflate
# "unknown failure vocabulary" with "unrepairable".
RULE_TABLE: Tuple[Tuple[str, List[Dict[str, Any]], str, str], ...] = (
    (
        "turnover",
        [{"type": "per_session_order_cap", "max_orders": 1}],
        "turnover",
        "throttle per-session order flow to suppress overtrading",
    ),
    (
        "risk",
        [{"type": "per_session_order_cap", "max_orders": 1}],
        "turnover",
        "throttle trading intensity to limit position accumulation "
        "behind risk-class failures",
    ),
    (
        "exposure",
        [{"type": "exposure_cap", "max_names_held": 1}],
        "gross_exposure_max",
        "restrict accumulation breadth to limit gross exposure "
        "behind exposure-class failures",
    ),
    (
        "concentration",
        [{"type": "per_session_order_cap", "max_orders": 1}],
        "turnover",
        "throttle trading intensity to limit position accumulation "
        "behind concentration-class failures",
    ),
    (
        "leverage",
        [{"type": "per_session_order_cap", "max_orders": 1}],
        "turnover",
        "throttle trading intensity to limit position accumulation "
        "behind leverage-class failures",
    ),
)

DEFAULT_RULES: Tuple[Dict[str, Any], ...] = (
    {"type": "per_session_order_cap", "max_orders": 1},
)
DEFAULT_RATIONALE = (
    "unlisted failure vocabulary: apply the v1 fallback guardrail "
    "(per-session order cap of one) and let validation judge"
)


class RepairProvider(Protocol):
    """Structural contract for repair-proposal generation."""

    @property
    def deterministic(self) -> bool:
        """True only if identical inputs imply identical proposals."""
        ...

    @property
    def method(self) -> str:
        ...

    @property
    def version(self) -> str:
        ...

    def propose(
        self,
        *,
        repair_id: str,
        diagnostic_id: str,
        baseline_evaluation_id: str,
        baseline_fingerprint: str,
        diagnostic_state_fingerprint: str,
        target_agent_identity: AgentIdentity,
        target_agent_fingerprint: str,
        hypothesis_id: str,
        hypothesis_fingerprint: str,
        failure_class: str,
        evidence_refs: Tuple[str, ...],
    ) -> RepairProposal:
        """Propose one constrained repair. Read-only: must not mutate inputs."""
        ...


class DeterministicRuleProvider:
    """v1 deterministic rule-table provider (method rule-table/v1)."""

    deterministic = True
    method = PROVIDER_METHOD
    version = PROVIDER_VERSION

    def propose(
        self,
        *,
        repair_id: str,
        diagnostic_id: str,
        baseline_evaluation_id: str,
        baseline_fingerprint: str,
        diagnostic_state_fingerprint: str,
        target_agent_identity: AgentIdentity,
        target_agent_fingerprint: str,
        hypothesis_id: str,
        hypothesis_fingerprint: str,
        failure_class: str,
        evidence_refs: Tuple[str, ...],
    ) -> RepairProposal:
        lowered = failure_class.lower() if isinstance(failure_class, str) else ""
        rules: List[Dict[str, Any]] = []
        rationale_fragment = ""
        target_metric = "turnover"
        for keyword, table_rules, target, fragment in RULE_TABLE:
            if keyword in lowered:
                rules = [dict(rule) for rule in table_rules]
                rationale_fragment = fragment
                target_metric = target
                break
        if not rules:
            rules = [dict(rule) for rule in DEFAULT_RULES]
            rationale_fragment = DEFAULT_RATIONALE
        return RepairProposal(
            repair_id=repair_id,
            diagnostic_id=diagnostic_id,
            baseline_evaluation_id=baseline_evaluation_id,
            baseline_fingerprint=baseline_fingerprint,
            diagnostic_state_fingerprint=diagnostic_state_fingerprint,
            target_agent_identity=target_agent_identity,
            target_agent_fingerprint=target_agent_fingerprint,
            hypothesis_id=hypothesis_id,
            hypothesis_fingerprint=hypothesis_fingerprint,
            failure_class=failure_class,
            evidence_refs=evidence_refs,
            target_metric=target_metric,
            target_direction=ExpectedDirection.DECREASE,
            method=self.method,
            method_version=self.version,
            parameters={"rules": rules},
            rationale=(
                f"v1 rule-table repair for failure class "
                f"{failure_class!r}: {rationale_fragment}."
            ),
            provenance={
                "provider": "DeterministicRuleProvider",
                "diagnostic_id": diagnostic_id,
                "baseline_evaluation_id": baseline_evaluation_id,
            },
        )
