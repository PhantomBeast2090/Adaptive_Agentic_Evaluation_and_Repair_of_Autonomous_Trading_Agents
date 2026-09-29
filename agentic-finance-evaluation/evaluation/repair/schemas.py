"""Repair-loop schemas (M-R0/M-R1, additive).

Canonical structured representations for the external memory/control-plane
repair loop. Every type here is a frozen dataclass fingerprinted with the
repository's existing canonicalisation
(``evaluation.contracts.fingerprints.fingerprint_of_dict``) — no second
hashing system.

Reuse map (no duplication):
  MemoryEntry enforcement state  -> StoredEntry + LearnedContext
                                   (evaluation/context/memory.py,
                                    evaluation/context/learned.py)
  Admission verdicts             -> AdmissionDecision / gate.adjudicate
  Candidate execution record     -> RepairedCandidate / RepairApplication
                                   (evaluation/diagnostics/repair/...)
  Verification triple            -> ValidationReport + RegressionAnalysis
                                    + RepairResult

New here (genuine gaps):
  FailureMechanism  validated, scoped diagnostic unit; compiler input.
  RepairSpec        compiled rule ops + scope + trigger + compiler version.
  MemoryEntry       structured canonical entry served by the control plane;
                    renders to LearnedContext for the frozen admission path.
  RepairCandidate   wrapper-level candidate handle (base + spec + shadow).
  RepairVerification single verdict handle over the verification triple.
  RepairVersion     store/rule/compiler version triple.
  RepairAuditRecord hash-chained append-only audit event.

Language discipline: nothing here "learns". Repairs are externally
memory-conditioned behavioural interventions on an unchanged policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze

SCHEMA_VERSION = "v1"
COMPILER_VERSION = "v1"
REPAIR_METHOD = "control-plane"
REPAIR_METHOD_VERSION = "v1"

# Rule vocabulary: M-R1 triple plus the M-R3-authorised max_quantity
# extension for loss-chasing escalation (bounded size truncation).
APPROVED_RULE_TYPES = (
    "per_session_order_cap",
    "exposure_cap",
    "hold_all",
    "max_quantity",
)

# Trigger clause operators. Clauses are (field, op, value) triples.
TRIGGER_OPERATORS = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in")

# Trigger fields readable from an observation payload + base orders.
# ``vix`` resolves via the frozen ``indiavix`` slot reader; ``*_present``
# inspect base-order sides; ``date`` is the decision_timestamp string.
TRIGGER_FIELDS = (
    "vix",
    "cash",
    "exposure",
    "buy_present",
    "sell_present",
    "date",
)


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_str_tuple(value: Any, name: str) -> Tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        items = tuple(value)
    else:
        raise TypeError(f"{name} must be a list/tuple of strings")
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"{name} must contain only strings")
    return items


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return fingerprint_of_dict(dict(payload))


@dataclass(frozen=True)
class FailureMechanism:
    """A validated, scoped diagnostic unit; the RepairCompiler input.

    ``taxonomy`` uses the frozen failure vocabulary (F-ACC/F-CONC/F-CASH/
    F-VOL from the diagnostic programme, or the provider rule-table keys
    turnover/risk/exposure/concentration/leverage). ``condition`` carries
    miner condition clauses verbatim where available. ``scope_hint`` and
    ``trigger_hint`` are advisory; the compiler validates them and falls
    back to UNCOMPILABLE rather than guessing.
    """

    mechanism_id: str
    taxonomy: str
    condition: Tuple[str, ...] = ()
    scope_hint: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    trigger_hint: Tuple[Tuple[str, str, Any], ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_str(self.mechanism_id, "mechanism_id")
        _require_str(self.taxonomy, "taxonomy")
        object.__setattr__(
            self, "condition", _require_str_tuple(self.condition, "condition")
        )
        object.__setattr__(
            self, "evidence_refs",
            _require_str_tuple(self.evidence_refs, "evidence_refs"),
        )
        if not self.evidence_refs:
            raise ValueError(
                "evidence_refs must be non-empty: a mechanism without "
                "evidence cannot compile to a repair"
            )
        if not isinstance(self.scope_hint, Mapping):
            raise TypeError("scope_hint must be a mapping")
        object.__setattr__(self, "scope_hint", freeze(dict(self.scope_hint)))
        validated_trigger = []
        for clause in self.trigger_hint:
            if (
                not isinstance(clause, (list, tuple))
                or len(clause) != 3
            ):
                raise TypeError(
                    "trigger_hint clauses must be (field, op, value) triples"
                )
            triple = (str(clause[0]), str(clause[1]), clause[2])
            _check_trigger_clause(triple)
            validated_trigger.append(triple)
        object.__setattr__(
            self, "trigger_hint", tuple(validated_trigger)
        )
        if not isinstance(self.provenance, Mapping):
            raise TypeError("provenance must be a mapping")
        if not dict(self.provenance):
            raise ValueError("provenance must be non-empty")
        object.__setattr__(self, "provenance", freeze(dict(self.provenance)))

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        from evaluation.contracts.fingerprints import thaw

        return {
            "mechanism_id": self.mechanism_id,
            "taxonomy": self.taxonomy,
            "condition": list(self.condition),
            "scope_hint": thaw(self.scope_hint),
            "trigger_hint": [list(c) for c in self.trigger_hint],
            "evidence_refs": list(self.evidence_refs),
            "provenance": thaw(self.provenance),
            "version": self.version,
        }


def _check_trigger_clause(clause: Tuple[str, str, Any]) -> None:
    field_name, op, _ = clause
    if field_name not in TRIGGER_FIELDS:
        raise ValueError(
            f"unknown trigger field {field_name!r}; "
            f"allowed: {list(TRIGGER_FIELDS)}"
        )
    if op not in TRIGGER_OPERATORS:
        raise ValueError(
            f"unknown trigger operator {op!r}; "
            f"allowed: {list(TRIGGER_OPERATORS)}"
        )


@dataclass(frozen=True)
class RepairScope:
    """Applicability scope for one compiled repair.

    Empty tuple/None means unconstrained on that axis. An entry fires only
    when every constrained axis matches the current decision context.
    """

    agent_id: str = ""
    instruments: Tuple[str, ...] = ()
    actions: Tuple[str, ...] = ()
    vix_band: Optional[Tuple[float, Optional[float]]] = None
    date_from: str = ""
    date_to: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str):
            raise TypeError("agent_id must be a string")
        object.__setattr__(
            self, "instruments",
            _require_str_tuple(self.instruments, "instruments"),
        )
        for action in self.actions:
            if action not in ("BUY", "SELL"):
                raise ValueError(
                    f"scope actions must be BUY/SELL, got {action!r}"
                )
        object.__setattr__(
            self, "actions", tuple(self.actions),
        )
        if self.vix_band is not None:
            lo, hi = self.vix_band
            if not isinstance(lo, (int, float)) or isinstance(lo, bool):
                raise ValueError("vix_band lo must be a number")
            if hi is not None:
                if not isinstance(hi, (int, float)) or isinstance(
                    hi, bool
                ):
                    raise ValueError("vix_band hi must be a number or None")
                if not lo < hi:
                    raise ValueError("vix_band requires lo < hi")
            object.__setattr__(
                self, "vix_band",
                (float(lo), None if hi is None else float(hi)),
            )
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must not precede date_from")

    def specificity(self) -> int:
        """Number of constrained axes; drives conflict resolution."""
        score = 0
        if self.agent_id:
            score += 1
        if self.instruments:
            score += 1
        if self.actions:
            score += 1
        if self.vix_band is not None:
            score += 1
        if self.date_from or self.date_to:
            score += 1
        return score

    def to_dict(self) -> dict:
        band = self.vix_band
        return {
            "agent_id": self.agent_id,
            "instruments": list(self.instruments),
            "actions": list(self.actions),
            "vix_band": [band[0], band[1]] if band is not None else None,
            "date_from": self.date_from,
            "date_to": self.date_to,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairScope":
        known = {"agent_id", "instruments", "actions", "vix_band",
                 "date_from", "date_to"}
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown RepairScope fields: {sorted(extra)}")
        band = payload.get("vix_band")
        return cls(
            agent_id=payload.get("agent_id", ""),
            instruments=tuple(payload.get("instruments", ())),
            actions=tuple(payload.get("actions", ())),
            vix_band=tuple(band) if band is not None else None,  # type: ignore[arg-type]
            date_from=payload.get("date_from", ""),
            date_to=payload.get("date_to", ""),
        )


@dataclass(frozen=True)
class RepairSpec:
    """Compiled, enforceable repair: rule ops + scope + trigger.

    ``rule`` entries use exactly the approved vocabulary enforced by
    ``GuardrailedAgent``. ``trigger`` clauses are ANDed; an empty trigger
    means "fire whenever scope matches".
    """

    spec_id: str
    mechanism_fingerprint: str
    rule_type: str
    rule_params: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    scope: RepairScope = field(default_factory=RepairScope)
    trigger: Tuple[Tuple[str, str, Any], ...] = ()
    priority: int = 0
    compiler_version: str = COMPILER_VERSION
    rationale: str = ""
    version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_str(self.spec_id, "spec_id")
        _require_str(self.mechanism_fingerprint, "mechanism_fingerprint")
        if self.rule_type not in APPROVED_RULE_TYPES:
            raise ValueError(
                f"rule_type {self.rule_type!r} not in approved M-R1 "
                f"vocabulary {list(APPROVED_RULE_TYPES)}"
            )
        if not isinstance(self.rule_params, Mapping):
            raise TypeError("rule_params must be a mapping")
        object.__setattr__(
            self, "rule_params", freeze(dict(self.rule_params))
        )
        if not isinstance(self.scope, RepairScope):
            raise TypeError("scope must be a RepairScope")
        checked = []
        for clause in self.trigger:
            triple = (str(clause[0]), str(clause[1]), clause[2])
            _check_trigger_clause(triple)
            checked.append(triple)
        object.__setattr__(self, "trigger", tuple(checked))
        if isinstance(self.priority, bool) or not isinstance(
            self.priority, int
        ):
            raise TypeError("priority must be an integer")

    def rule(self) -> dict:
        """The GuardrailedAgent-compatible rule mapping."""
        return {"type": self.rule_type, **dict(self.rule_params)}

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        from evaluation.contracts.fingerprints import thaw

        return {
            "spec_id": self.spec_id,
            "mechanism_fingerprint": self.mechanism_fingerprint,
            "rule_type": self.rule_type,
            "rule_params": thaw(self.rule_params),
            "scope": self.scope.to_dict(),
            "trigger": [list(c) for c in self.trigger],
            "priority": self.priority,
            "compiler_version": self.compiler_version,
            "rationale": self.rationale,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairSpec":
        known = {"spec_id", "mechanism_fingerprint", "rule_type",
                 "rule_params", "scope", "trigger", "priority",
                 "compiler_version", "rationale", "version"}
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown RepairSpec fields: {sorted(extra)}")
        return cls(
            spec_id=payload["spec_id"],
            mechanism_fingerprint=payload["mechanism_fingerprint"],
            rule_type=payload["rule_type"],
            rule_params=dict(payload.get("rule_params", {})),
            scope=RepairScope.from_dict(payload.get("scope", {})),
            trigger=tuple(tuple(c) for c in payload.get("trigger", ())),
            priority=payload.get("priority", 0),
            compiler_version=payload.get("compiler_version",
                                         COMPILER_VERSION),
            rationale=payload.get("rationale", ""),
            version=payload.get("version", SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MemoryEntry:
    """Structured canonical memory entry served by the control plane.

    This is the enforcement source of truth (never free text). It renders
    to a ``LearnedContext`` for the frozen admission path via
    :meth:`to_learned_context`, which serialises the spec deterministically
    into the string-slot contract the store requires.
    """

    entry_id: str
    agent_id: str
    spec: RepairSpec
    source_evaluation_id: str
    diagnostic_evidence: Tuple[str, ...] = ()
    priority: int = 0
    sequence: int = 1
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_str(self.entry_id, "entry_id")
        _require_str(self.agent_id, "agent_id")
        if not isinstance(self.spec, RepairSpec):
            raise TypeError("spec must be a RepairSpec")
        object.__setattr__(
            self, "diagnostic_evidence",
            _require_str_tuple(
                self.diagnostic_evidence, "diagnostic_evidence"
            ),
        )
        if not self.diagnostic_evidence:
            raise ValueError("diagnostic_evidence must be non-empty")
        if isinstance(self.priority, bool) or not isinstance(
            self.priority, int
        ):
            raise TypeError("priority must be an integer")
        if isinstance(self.sequence, bool) or not isinstance(
            self.sequence, int
        ) or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if not isinstance(self.provenance, Mapping) or not dict(
            self.provenance
        ):
            raise ValueError("provenance must be a non-empty mapping")
        object.__setattr__(self, "provenance", freeze(dict(self.provenance)))

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        from evaluation.contracts.fingerprints import thaw

        return {
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "spec": self.spec.to_dict(),
            "source_evaluation_id": self.source_evaluation_id,
            "diagnostic_evidence": list(self.diagnostic_evidence),
            "priority": self.priority,
            "sequence": self.sequence,
            "provenance": thaw(self.provenance),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MemoryEntry":
        known = {"entry_id", "agent_id", "spec", "source_evaluation_id",
                 "diagnostic_evidence", "priority", "sequence",
                 "provenance", "version"}
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown MemoryEntry fields: {sorted(extra)}")
        return cls(
            entry_id=payload["entry_id"],
            agent_id=payload["agent_id"],
            spec=RepairSpec.from_dict(payload["spec"]),
            source_evaluation_id=payload["source_evaluation_id"],
            diagnostic_evidence=tuple(
                payload.get("diagnostic_evidence", ())),
            priority=payload.get("priority", 0),
            sequence=payload.get("sequence", 1),
            provenance=dict(payload.get("provenance", {})),
            version=payload.get("version", SCHEMA_VERSION),
        )

    def to_learned_context(
        self,
        status: Any,
        validation_result: str,
        validation_metrics: Mapping[str, Any] | None = None,
        held_out_evidence: Mapping[str, Any] | None = None,
    ) -> Any:
        """Render to the frozen LearnedContext admission contract.

        Validation evidence is a REQUIRED argument (never defaulted):
        rendering happens at admission time with real validation results,
        so an empty placeholder can never slip into the store.
        """
        import json

        from evaluation.context.learned import LearnedContext

        if not isinstance(validation_result, str) or not validation_result:
            raise ValueError(
                "validation_result must be a non-empty string: rendering "
                "requires real validation evidence"
            )
        spec_json = json.dumps(
            self.spec.to_dict(), sort_keys=True, separators=(",", ":")
        )
        return LearnedContext(
            context_id=self.entry_id,
            agent_id=self.agent_id,
            source_evaluation_id=self.source_evaluation_id,
            failure_mechanism=self.spec.mechanism_fingerprint,
            observed_pattern=";".join(self.diagnostic_evidence),
            triggering_conditions=tuple(
                f"{f} {op} {v}" for f, op, v in self.spec.trigger
            ),
            diagnostic_evidence=self.diagnostic_evidence,
            corrective_principle=spec_json,
            applicability_conditions=(
                f"scope={json.dumps(self.spec.scope.to_dict(), sort_keys=True)}",
            ),
            contraindications=(),
            expected_effect=f"rule={self.spec.rule_type}",
            validation_result=validation_result,
            validation_metrics=dict(validation_metrics or {}),
            held_out_evidence=dict(held_out_evidence or {}),
            provenance=dict(self.provenance),
            status=status,
        )


@dataclass(frozen=True)
class RepairCandidate:
    """Wrapper-level candidate handle: base agent + spec + shadow evidence."""

    candidate_id: str
    base_agent_fingerprint: str
    spec_fingerprint: str
    wrapper_fingerprint: str = ""
    shadow_fingerprint: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_str(self.candidate_id, "candidate_id")
        _require_str(self.base_agent_fingerprint, "base_agent_fingerprint")
        _require_str(self.spec_fingerprint, "spec_fingerprint")
        if not isinstance(self.provenance, Mapping):
            raise TypeError("provenance must be a mapping")
        object.__setattr__(self, "provenance", freeze(dict(self.provenance)))

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        from evaluation.contracts.fingerprints import thaw

        return {
            "candidate_id": self.candidate_id,
            "base_agent_fingerprint": self.base_agent_fingerprint,
            "spec_fingerprint": self.spec_fingerprint,
            "wrapper_fingerprint": self.wrapper_fingerprint,
            "shadow_fingerprint": self.shadow_fingerprint,
            "provenance": thaw(self.provenance),
            "version": self.version,
        }


@dataclass(frozen=True)
class RepairVerification:
    """Single verdict handle over the verification triple.

    ``validation_fingerprint`` / ``regression_fingerprint`` /
    ``decision_fingerprint`` reference the frozen
    ValidationReport/RegressionAnalysis/RepairResult artefacts. ``verdict``
    defaults to NSF: insufficient evidence never commits.
    """

    verification_id: str
    candidate_fingerprint: str
    validation_fingerprint: str = ""
    regression_fingerprint: str = ""
    decision_fingerprint: str = ""
    metric_deltas: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    bootstrap_ci: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    persistence_fingerprint: str = ""
    verdict: str = "NSF"
    provenance: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_str(self.verification_id, "verification_id")
        _require_str(self.candidate_fingerprint, "candidate_fingerprint")
        if self.verdict not in ("ACCEPT", "REJECT", "NSF"):
            raise ValueError(
                f"verdict must be ACCEPT/REJECT/NSF, got {self.verdict!r}"
            )
        for name in ("metric_deltas", "bootstrap_ci", "provenance"):
            if not isinstance(getattr(self, name), Mapping):
                raise TypeError(f"{name} must be a mapping")
        object.__setattr__(
            self, "metric_deltas", freeze(dict(self.metric_deltas))
        )
        object.__setattr__(
            self, "bootstrap_ci", freeze(dict(self.bootstrap_ci))
        )
        object.__setattr__(self, "provenance", freeze(dict(self.provenance)))

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        from evaluation.contracts.fingerprints import thaw

        return {
            "verification_id": self.verification_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "validation_fingerprint": self.validation_fingerprint,
            "regression_fingerprint": self.regression_fingerprint,
            "decision_fingerprint": self.decision_fingerprint,
            "metric_deltas": thaw(self.metric_deltas),
            "bootstrap_ci": thaw(self.bootstrap_ci),
            "persistence_fingerprint": self.persistence_fingerprint,
            "verdict": self.verdict,
            "provenance": thaw(self.provenance),
            "version": self.version,
        }


@dataclass(frozen=True)
class RepairVersion:
    """Version triple identifying one repair configuration."""

    store_sequence: int
    rule_table_version: str
    compiler_version: str = COMPILER_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.store_sequence, bool) or not isinstance(
            self.store_sequence, int
        ):
            raise TypeError("store_sequence must be an integer")
        _require_str(self.rule_table_version, "rule_table_version")
        _require_str(self.compiler_version, "compiler_version")

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        return {
            "store_sequence": self.store_sequence,
            "rule_table_version": self.rule_table_version,
            "compiler_version": self.compiler_version,
        }


@dataclass(frozen=True)
class RepairAuditRecord:
    """One hash-chained append-only audit event.

    No wall-clock timestamps (determinism): ordering is the logical
    ``seq`` plus ``prev_hash`` chain. ``event`` names the transition
    (COMPILED/SHADOWED/VALIDATED/ADMITTED/ACTIVATED/DEACTIVATED/ROLLED_BACK).
    """

    seq: int
    prev_hash: str
    event: str
    payload: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if isinstance(self.seq, bool) or not isinstance(self.seq, int):
            raise TypeError("seq must be an integer")
        _require_str(self.prev_hash, "prev_hash")
        _require_str(self.event, "event")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", freeze(dict(self.payload)))

    def event_hash(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict:
        from evaluation.contracts.fingerprints import thaw

        return {
            "seq": self.seq,
            "prev_hash": self.prev_hash,
            "event": self.event,
            "payload": thaw(self.payload),
        }
