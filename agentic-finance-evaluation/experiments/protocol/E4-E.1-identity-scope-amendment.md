# E4-E.1 Amendment — Identity-Scope Attestation

**Amends:** E4-E orchestration only (`run_e4e` delivery-scope seam).
**Status:** frozen pending review.
**Scope:** one additive E4 module, one orchestration call-site, lineage
bagging, tests. No endpoint, criterion, window, metric, budget,
retrieval, admission, or leakage change.

Use British English in all E4-E.1 reporting.

## 1. Incident

The first controlled E4-E execution (harness `574e77d9…`,
`SYSTEM_VALIDATION`/`001`, Feb/Mar 2023) produced an ACCEPTED turnover
repair, admitted K1 to C1, locked C1, and passed leakage attestation —
then halted before any arm episodes: K1 carries
`volatility-threshold-benchmark@1.0` (the repair target), while E4 arms
evaluate `contextual-threshold-benchmark@1.0` (the context-enabled
representation, necessarily outside frozen `benchmarks/`). Exact-match
retrieval returned empty and every layer failed closed correctly. No
arm data was generated; no artefact was fabricated.

## 2. Consequence

The halt is preserved as integrity evidence. It establishes a
protocol-design gap, not a code defect: the E4-E protocol never named
either identity and implicitly assumed repair-target identity equals
delivery-target identity. Retrieval exactness is not the cause and is
not changed by this amendment.

## 3. Resolution

E4-E.1 introduces an E4-owned `IdentityScopeAttestation`
(`evaluation/context/identity_scope.py`, method
`identity-scope-attestation/v1`) plus `resolve_delivery_scope()`,
invoked at exactly one seam in `run_e4e` (post-`admit`, pre-`retrieve`).
The resolver returns the attested source string used as the
exact-match retrieval key; the probe's own identity continues to
`assemble()`/`deliver()` unchanged, so the `deliver()` cross-agent
refusal remains an intact backstop.

## 4. What the attestation binds

Repair source id/version (parsed from the candidate, cross-checked
against the live proposal identity object and the candidate's recorded
proposal fingerprint); delivery id/version (live probe identity, fresh
and uncontextualised); source base-policy fingerprint (fresh instance,
pinned to manifest `db16e4a8…`); delivery base-policy proof (nine
frozen constants asserted live, pinned to `class_b_constants`;
shared readers; adapt-surface asymmetry); knowledge lineage
(candidate/admitted/verdict/store fingerprints). Deliberately NOT
bound: `target_agent_fingerprint` (repair-time state snapshot —
volatile `calls` make it ordering-sensitive; the fresh-instance plus
manifest pin plus `reset()` convention is the stable binding).

## 5. Closed v1 scope

Approved source: `volatility-threshold-benchmark@1.0` only. Approved
delivery: `contextual-threshold-benchmark@1.0` only. Any deviation —
identities, versions, constants, fingerprints, provenance, store
lineage — fails closed. Widening is a versioned change.

## 6. Non-claim

The attestation establishes execution-lineage scope sufficient for
contextual delivery. It does NOT establish behavioural equivalence,
which remains empirical (C0 branch-matrix equivalence is tested
separately and covers boundaries, cash gates, reduce paths, malformed
inputs, and call-count parity).

## 7. Unchanged

Windows, metrics, budgets, E2-F geometry, E4-A–D semantics, admission
rules, leakage rules, arm methodology, Tier-1 artefacts (the halted
execution record stands unmodified).

## 8. Entry criteria for re-execution

All E4 context suites green; boundary scans green; full repository
suite green at the freeze boundary; this amendment reviewed and
frozen. Re-execution reuses the preserved Feb/Mar windows and requires
no new K1 derivation design (a fresh K1 will be derived live by the
rerun itself).
