# E4-E: Controlled Context-Repair Experiment

**Milestone:** E4-E (four-arm controlled comparison; descriptive, n=1).
**Status:** protocol frozen pending review. No objective comparison has
been executed under this protocol at the time of freezing.
**Claim ceiling:** E4-E tests whether validated context delivery changes
agent behaviour and whether persistent context is distinguishable from
temporary instruction. Not self-repair.

Use British English in all E4-E reporting.

## 1. Research objective

Determine whether validated corrective knowledge derived from an
agent's failure alters its subsequent behaviour when delivered through
context, and whether any effect differs across no knowledge, diagnosis
without delivery, temporary instruction, and persistent validated
learned context.

## 2. Hypotheses (H1–H4, none assumed true)

* H1: validated context changes mechanism-specific behaviour.
* H2: persistent C1 is experimentally distinguishable from temporary
  corrective instruction.
* H3: context delivery changes the relevant objective/risk/constraint
  profile.
* H4: the observed behavioural effect persists on the held-out window.

## 3. Frozen dependencies

E0 contracts (`TargetAgent`, `adapt` seam, fingerprints), E1
`run_baseline` plus the 25-metric inventory, E2 diagnostic semantics,
E2-F repair plus three-run validation geometry plus ledger, the Indian
environment with strict t−1 PIT and venue calendars, E3-C.2 manifest
plus E3-D.1 overlay, E3-D Tier-1 descriptive discipline, and E4-A–D
(`LearnedContext`, extraction, gate, `MemoryStore`, retrieval v1,
assembly, store-bound delivery, contextual benchmark). E4-E adds
orchestration only.

## 4. E3-D.1 window justification

Reuse the active pair: diagnostic 2023-02-01→02-28 (20 NSE_CM
sessions, env `60d189e4…`), held-out 2023-03-01→03-31 (21 sessions,
env `484b82a7…`). The pair was selected blind on presence-only
session counts, is strictly later and non-overlapping, carries the
unchanged universe/costs/cash/PIT/vintage/pool/budgets, and maps
exactly onto diagnostic learning versus held-out testing. No fresh
blind pair is required. The retired May/Jul pair must never enter
E4-E tables or framing.

## 5. Four-arm design

* **A — C0 baseline:** contextual benchmark, empty store, no `adapt()`.
* **B — diagnosis-only:** validated repair artefacts retained for
  provenance; `corrective_context_delivered=false`; no `adapt()`.
* **C — temporary context:** equivalent corrective entries via one
  provisional `adapt()` (`provisional:true`,
  `provenance:"temporary-no-store"`) on an isolated copy; no store,
  no retrieval, no package, no verdicts, no `mem-*` identifiers, no
  persistence beyond the episode.
* **D — persistent C1:** `extract_candidate → adjudicate → admit →
  retrieve → assemble → deliver → evaluate` with C1 locked before any
  held-out run; admitted validated knowledge only.

## 6. Information available to each arm

All arms share agent build, base policy, configs, windows, metrics,
and determinism controls. A receives base policy plus live
observations. B additionally retains diagnostic provenance. C
additionally receives corrective entry contents ephemerally. D
additionally receives the full admitted lineage through the
store-bound path.

## 7. Forbidden information

No arm modifies weights, code, architecture, or optimiser state. A/B
receive no corrective entries. C receives no store lineage and leaves
no persistent state. D receives no hand-built entries and no
retrieval-v2 signals. Held-out outcomes are forbidden during K1
derivation, and retired-pair values are forbidden throughout.
`evaluators/` is forbidden as an execution path for all arms.

## 8. Leakage controls

Order: diagnostic evaluation → diagnosis → repair → validation →
extract K1 → adjudicate → admit → lock C1 → attest lock → held-out
A/B/C/D evaluation. `check_window_order` enforces
`heldout_start > diagnostic_end` before any execution; `attest_leakage`
binds the locked store/package fingerprints to the temporal order in
the artefact. On any violation: halt, no silent repair.

## 9. K1 derivation

K1 originates exclusively from already-validated E2-F artefacts via
`extract_candidate(proposal, result, report, analysis)` with
cross-artefact linkage checks. No invented evidence; held-out outcomes
restated only as recorded validation evidence, never newly mined.

## 10. C1 admission

`adjudicate()` judges the CANDIDATE only, requires ACCEPTED, checks
provenance lineage plus proposal linkage, and handles
DUPLICATE/QUARANTINE. `MemoryStore.admit()` appends one entry
(`C0 → C1`), immutable and fingerprinted. Non-admitted K1 halts the
campaign rather than degrading into hand-built context.

## 11. Lock protocol

`lock_c1` records `store_fingerprint_at_lock`,
`package_fingerprint_at_lock`, and `retrieved_ids_at_lock` with no
clock input. The lock is attested before held-out execution; post-lock
modification, re-extraction, re-admission, retrieval redesign, or
principle edits are forbidden.

## 12. Lineage schema

`E4EResult.lineage` carries proposal, repair-result, validation,
analysis, candidate, verdict, C0/C1 store, retrieval, package,
temporary-payload, and per-window delivery fingerprints.
`E4EResult.arms[arm][window]` carries evaluation id and fingerprint,
before/after agent fingerprints, the full metric map, and the context
descriptor. `E4EResult.leakage` carries the attestation.

## 13. Metrics

All 25 frozen E1 metrics per arm per window, `None`-preserving.
Focus: mechanism (`turnover`, `order_count`, `executed_notional`,
`transaction_cost_total`, `reversal_rate`, held-name repeat-BUY
counts); exposure (`gross/net/leverage`, concentration, persistence);
activity (`inactivity_rate`); validity (seven count/rate metrics);
outcomes (`cumulative_return`, volatility, Sharpe, Sortino,
`max_drawdown`, worst session) descriptively.

## 14. Regression guards

`check_guards` flags validity zero→positive, inactivity collapse, and
mechanism-opposite turnover movement. Flags are descriptive; no
numerical thresholds are invented and no success is adjudicated.

## 15. Determinism

Canonical freeze, sorted-keys compact JSON, SHA-256 throughout;
unknown-field rejection on every contract; seeds provenance-only; no
wall-clock, UUID, PID, randomness, or hidden counters in identity
paths; fresh agent/store/delivery instances per arm per window;
trajectory-fingerprint equality is reproduction, not replication.

## 16. Descriptive statistics (n=1)

One complete agent×protocol×window execution is one unit. Report
matched `B − A` deltas (`None` when either side is undefined) for
`A_vs_D`, `A_vs_C`, `C_vs_D`, `B_vs_C` per window. No p-values, no
confidence intervals, no pooling across sessions or trades, no
population claims. A null result (`A ≈ C ≈ D`) is valid.

## 17. Failure conditions

Non-admitted K1, quarantined/duplicated knowledge, guard regressions,
delivery refusals, missing metrics behaviour (recorded as `None`,
never imputed), and environment failures are reported explicitly with
their fingerprints. Mixed results are reported as mixed.

## 18. Stop conditions

Halt and report if E0–E3 modification becomes necessary, E4-A–D
semantics must change, retrieval-v2 appears necessary, held-out
leakage is detected, frozen artefacts would be overwritten,
`evaluators/` is required, success thresholds would need inventing,
context must be hand-fabricated, the benchmark must change, or
deterministic fingerprints cannot be maintained.

## 19. Result artefact layout

`results/e4/<experiment_id>/<execution_id>.json` where the execution
id binds experiment id, role, and instance. `save_e4e_result`
refuses non-`results/e4/` paths and refuses overwrites. E3 artefacts
are never written from E4-E.

## 20. E4-F entry criteria

E4-F (retrieval-v2, multi-memory, conflicts, C1→C2 cycles) requires:
measurable A-vs-D mechanism effect; interpretable C-vs-D
relationship; no guard regressions; held-out directional persistence;
and a concrete retrieval limitation demanding selective retrieval.
Otherwise stop at E4-E.
