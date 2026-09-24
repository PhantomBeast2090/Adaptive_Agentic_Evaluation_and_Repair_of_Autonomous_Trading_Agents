# E4-D: Contextual Delivery Protocol

**Milestone:** E4-D (delivery machinery + contextual benchmark; no
objective comparison).
**Status:** frozen pending review. Establishes the context-to-behaviour
pathway only. Whether delivered knowledge improves the trading
objective is an E4-E empirical question, explicitly out of scope.
**Claim ceiling:** validated learned context can be retrieved and
delivered to an otherwise unchanged agent and can alter its behaviour
under the defined conditions. Not self-repair.

## 1. Objective and research question

Can validated failure knowledge, persisted through the E4-A–E4-C
chain, be delivered into an agent's accessible reasoning context so
that the same agent behaves differently under identical observations?
E4-D answers the delivery half; E4-E will ask whether the difference
helps the objective.

## 2. Scope and frozen dependencies

E0 contracts (TargetAgent, AgentIdentity, fingerprints), E1 metrics,
E2 diagnostic/repair/validation semantics, Indian environment and
calendars, E3-C benchmarks/manifest (volatility-threshold@1.0,
universe, VIX 15.0/25.0 conventions), E3-D/E3-D.1 protocol, E4-A–E4-C
contracts. E4-D adds behaviour, changes nothing frozen.

## 3. Agent interface

E0 `adapt(intervention: Mapping) -> None`, optional and never invoked
by evaluator machinery. `reset()` clears episode-local state and
preserves adaptation memory (frozen contract language). Delivery is
the sole production caller of `adapt()`; E2-F repair, orchestration,
and baseline paths contain zero `.adapt(` calls (scan-enforced).

## 4. Retrieval method (v1)

Exact `agent_id` match over admitted store entries, deterministic
sequence order (`context-retrieve/v1`). No embeddings, ranking, or
stochasticity. Contraindications travel in the package but do not
gate v1 retrieval; selective use is a versioned future change.

## 5. Context assembly

`ContextPackage`: agent identity, store fingerprint, retrieved ids,
per-entry mechanism/pattern/triggering/corrective/applicability/
contraindications/effect/validation/fingerprint/version, method
versions, SHA-256 fingerprint (`context-assemble/v1`). Structured
provenance, never a text dump.

## 6. Delivery method

Identity agreement check → deep copy → exactly one `adapt()` with
`{context_package_fingerprint, entries}` → `(adapted, DeliveryRecord)`
binding before/after agent fingerprints to the package fingerprint
(`context-deliver/v1`). Original and store never mutated.

## 7. Isolation guarantees

Copy-on-write delivery; original fingerprint equality before/after;
store fingerprint equality before/after; reset clears episode
counters only; learned context survives reset (tested).

## 8. Reset semantics

Episode state (`calls`) vs learned context (`learned_contexts`)
separation is structural: `reset()` touches only the former.
C1 availability across episodes is therefore mechanical, and tested
across reset boundaries.

## 9. Metrics to be measured later (E4-E, not here)

Mechanism family (turnover, order_count, executed_notional,
transaction_cost_total, reversal_rate), exposure/concentration,
activity, validity, trading outcomes — the frozen E1 inventory.
No thresholds, no success criteria, no comparisons in E4-D.

## 10. Deterministic provenance

LearnedContext → MemoryStore → RetrievalRecord → ContextPackage →
DeliveryRecord → agent-before/after fingerprints. Every link
fingerprinted; cross-process determinism tested. Any replay answers
what the agent knew, why, from which evaluation, why admitted, why
retrieved, what was delivered, and what was decided.

## 11. Acceptance criteria (E4-D complete iff)

Retrieval/assembly/delivery/determinism/isolation/behavioural/
adversarial/boundary suites green; E0–E3 byte-identical;
Tier-1 artefacts untouched; no objective comparison performed.

## 12. Limitations

Single mechanism exercised end-to-end (turnover); retrieval is
agent-scoped, not regime-conditioned; contraindications carried
but unenforced; no C0/C1 objective comparison (E4-E); no repeated
cycles (E4-F+); contextual benchmark is an instrument, not a
trading advance.
