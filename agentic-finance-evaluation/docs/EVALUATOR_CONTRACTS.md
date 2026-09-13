# E0 — Evaluator Contracts

Status: contract layer (milestone E0). Representations only — no baseline
evaluator (E1), no adaptive diagnosis (E2), no repair (E3), no learning
(E4), no LLM anywhere.

Package: `evaluation/contracts/` (plural, matching `evaluation/evaluators/*`
and `evaluation/adaptive/*`). There is deliberately no top-level
`evaluator/` package.

## What each contract represents and why it exists

* **Agent** (`agent.py`): `AgentIdentity` (frozen id/version) plus the
  `TargetAgent` structural `Protocol` (`identity`, `reset()`,
  `act(TargetObservation) -> order list`). Lets E1/E2 drive heterogeneous
  agents without inheriting a class hierarchy. `validate_target_agent`
  returns error lists (never raises, never calls `act`); `invoke_act` is
  the single invocation path and accepts only `TargetObservation`.
* **DecisionRecord** (`decision_record.py`): one immutable raw observable
  event — timestamp, state fingerprint, visible/unavailable assets,
  submitted orders, reason-coded validation, `OrderResult` copies,
  portfolio before/after, `reward = total_equity_after -
  total_equity_before` (enforced exactly), environment metadata carrying
  `market_fingerprint`. Copied from environment outputs, never recomputed.
* **BehavioralEvidence** (`evidence.py`): one derived, categorized claim
  (`EvidenceCategory`: RISK/TEMPORAL/MARKET_REGIME/DECISION_BEHAVIOR/
  INFORMATION_USAGE/ROBUSTNESS/EXECUTION). References raw records by
  fingerprint, names its derivation method, leaves `value=None` explicit
  with a reason instead of fabricating substitutes.
* **Hypothesis** (`hypotheses.py`): one falsifiable mechanism claim.
  `failure_class` (observed symptom) and `mechanism` (candidate cause) must
  differ — observed failure is not proven mechanism. Competing hypotheses
  may share evidence; lifecycle (`PROPOSED/SUPPORTED/WEAKENED/REJECTED/
  UNRESOLVED`) advances via pure `with_status` copies. Non-proposed
  hypotheses must cite evidence.
* **DiagnosticTest** (`diagnostic_tests.py`): one immutable test
  specification — targets, `intervention` descriptor (requires `type`),
  measures, expected discrimination, non-negative cost, preconditions.
  Describes interventions; implements none.
* **EvaluationState** (`evaluation_state.py`): the accumulative record
  (ids, frozen environment spec incl. `market_fingerprint`, config,
  budget, baseline/derived evidence, hypotheses, executed tests + results,
  opaque repair/validation/regression placeholders, stopping reason).
  Mutable only through append-only methods; internal tuples are replaced,
  never mutated; test results require a recorded test; ids are unique;
  stopping is set once. Round-trips through `to_dict`/`from_dict`.
* **EvaluationBudget** (`budget.py`): five explicit limits, including
  `max_runtime` (`None` = unbounded, passed explicitly; zero = allow none).
  Negatives,
  bools, and non-ints raise. `is_exhausted`/`remaining` are pure
  predicates; enforcement belongs to E2.
* **StoppingReason** (`stopping.py`): six-member string enum with
  fail-closed `from_str`. Vocabulary only, no stopping logic.
* **Fingerprints** (`fingerprints.py`): shared canonicalization
  (`json.dumps(sort_keys=True, separators=(",",":"))`, floats via `repr`)
  plus SHA-256. Sets/bytes/NaN/Infinity and non-string mapping keys are
  rejected so they can never enter an identity silently.

## Important invariants

* Frozen dataclasses everywhere except `EvaluationState` (accumulator) and
  `TargetObservation` (validated snapshot view).
* Fail-closed validation: malformed inputs raise (`ValueError` for bad
  values, `TypeError` for wrong types); unknown enum strings and unknown
  serialization fields are rejected, never defaulted.
* `agent_metadata` on `DecisionRecord` is whitelisted to
  (`confidence`, `rationale`, `tool_calls`, `retrieved_information`).
  There is no chain-of-thought field; the evaluator works from observable
  behavior.
* `reward` equality, disjoint visible/unavailable assets, grounded
  non-proposed hypotheses, and no-orphan test results are enforced at
  construction, not by convention.

## Leakage boundary

`TargetObservation` wraps **only** an actual `EnvironmentState` instance
from the existing Indian environment (closed five-key schema and exact
slot schemas). It has no public constructor, and serialized dictionaries
are rejected. `OraclePacket` (`evaluator_only=True` enforced) has no
conversion path to a target observation; `invoke_act` rejects packets and
plain mappings with `TypeError`. Provenance is structural (construction
path + closed schema), not cryptographic; deliberate object forgery is out
of scope.
`InformationSet` and temporal eligibility are untouched.

## What E0 deliberately does NOT do

No episode runner, no metric computation, no hypothesis formation, no
test selection/execution, no intervention implementation, no repair, no
validation logic beyond opaque placeholders, no LLM/API/network/database
dependencies, no environment or data changes.
