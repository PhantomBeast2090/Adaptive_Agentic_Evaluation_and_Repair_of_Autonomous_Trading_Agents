# E4-F: Accumulation Cycles Protocol

**Milestone:** E4-F (multi-cycle retention/accumulation; descriptive, n=1).
**Status:** protocol frozen pending review. No multi-cycle episodes have
been executed under this protocol at the time of freezing.
**Claim ceiling:** whether independently validated corrective contexts
accumulate across cycles in one store and jointly influence behaviour
of unchanged agents, distinguishable from dual temporary instruction.

Use British English in all E4-F reporting.

## 1. Research objective

Determine whether validated corrective knowledge persists across
successive evaluation–diagnosis–repair cycles, accumulates with newly
validated knowledge, and jointly influences later behaviour — beyond
what equivalent temporary instructions produce.

## 2. Hypotheses (none assumed true)

* H1: K1 is retained byte-identical into Cycle 2 (retrievable, listed,
  behaviourally active).
* H2: K2 is independently validated and admitted (distinct identity,
  provenance, lineage; duplicate-refused against K1).
* H3: C1+C2 joint behaviour separates from T12 dual-temporary
  instruction on the terminal window.
* H4: mechanism corrections (turnover depth, exposure breadth) persist
  without guard regressions.

## 3. Frozen dependencies

E0 contracts, E1 25 metrics, E2 diagnostics, E2-F repair as amended
(exposure_cap rule, exposure-routed provider, two-hypothesis
transcription), E3 harness, E4-A–D, E4-E orchestration, E4-E.1 scope
attestation (v1 unchanged; v2 admits the dual-guard representation).

## 4. Mechanisms

M1: turnover / LOW-regime repeat accumulation / order-cap correction,
validated against `turnover`, DECREASE. M2: exposure / holdings
breadth / breadth-cap correction (`exposure_cap/max_names_held`),
validated against `gross_exposure_max`, DECREASE. The two guards have
orthogonal geometry (depth vs breadth) pinned by divergence tests.

## 5. Windows

A fresh blind 3-window sequence (W1<W2<W3) is required: Feb/Mar 2023
are scientifically unusable (outcomes published; replay is not
replication); the retired pair is forbidden. Each window must satisfy
the frozen admissibility rule (≥20 NSE_CM sessions, 0 UNKNOWN, ≥20
gold presence-only dates, strict non-overlap, outcome-blind selection)
under a new supplement anchoring to `manifest.e4f.yaml`. The overlay's
carried temporal values never govern an execution.

## 6. Cycle design (R/P/V/A)

* Cycle 1 on W1: frozen single-cycle pipeline for M1 → locked C1.
* Cycle 2, branch R (C0 agent on W2): sole source of K2 diagnostic
  evidence. Branch P (C1 agent on W2): retention read only; its
  observations never enter K2 provenance. Branch V: frozen 3-run
  validation geometry for K2. Admission into the C1-seeded store → C2.
* Terminal on W3: C0 / T1 / C1 / T12 / C1+C2 reads.
* Repair targeting per cycle: exactly-one-SUPPORTED selection
  (`repair_target_hypothesis`); ambiguity halts the cycle rather than
  cherry-picking.

## 7. Arms and decisive contrast

Terminal conditions C0, T1, C1, T12 (dual temporary, store-free),
C1+C2. The decisive contrast is C1+C2 vs T12 with identical entry
contents: separation plus K1 byte-retention plus K2 independent
validation is required before any accumulation language.

## 8. Success rule (pre-registered)

Jointly: (i) mechanism endpoints move in validated directions on
held-out, (ii) no guard trips (validity zero→positive, inactivity
collapse, mechanism-opposite), (iii) non-inferiority on
`cumulative_return` and `max_drawdown` vs C0, (iv) C1+C2 separates
from T12. Non-inferiority is a safety criterion, not success.
Behaviour change without outcome support is reported as adaptation,
never as self-repair success.

## 9. Falsifiers

C1+C2 ≡ T12; K1 altered/absent; K2 refused on merit; any guard trip;
C0-equivalence failure of either instrument; leakage attestation
failure; duplicate admission.

## 10. Leakage

Per-cycle Cn locks before later-window reads; K2 blind to W3 and
Cycle-1 outcomes; attestation per admission; amendment widening
limited to window/surface additions with clock restart.

## 11. Determinism and isolation

Canonical fingerprints throughout; fresh agent/store/delivery
instances per arm/window/cycle; trajectory equality is reproduction,
not replication.

## 12. Result artefact

Cycle-indexed arms, per-cycle locks and attestations, full per-cycle
lineage (`E4FCycleResult`), persisted under a cycle namespace with
refuse-overwrite semantics.

## 13. Limitations

Single window triple, two mechanisms, n=1 descriptive slice;
discovery-interaction (does C1 alter M2 discovery?) explicitly
deferred; generality, profitability, and readiness out of scope.
