# E3-E Harness Protocol (Operator Guide)

**Scope:** execution orchestration for the frozen E3-D Tier-1 protocol.
**Status:** implementation guide; introduces no scientific decisions.
**Package:** `experiments/harness/` · **Artefacts:** `results/e3/<experiment_id>.json`
· **Tests:** `tests/experiments/harness/`.

## 1. Architecture

E3-D (frozen) → `experiments/harness/` → frozen E0–E2 primitives →
frozen Indian environment. The harness owns configuration, identity,
lineage, gating, persistence, and reproduction. It owns no metric,
execution-semantic, interpretation, selection, repair, or validation
logic. D-F and D-A share one `diagnose()` executor; the policy seam
is manifest order vs the frozen E2-D selector, and everything after
selection (execute → interpret → record) is the identical shared path.

## 2. Arm identifiers and transitions

`N-D` (original/diagnostic), `N-H` (original/held-out, sealed),
`D-F`, `D-A`, `R-D`, `R-H`. No generic H exists. Allowed: `N-D→D-F`,
`N-D→D-A`, `N-H→SEALED`, `D→REPAIR`, `REPAIR→R-D` (completed repair +
real validation fingerprint only; FAILED never yields R-D),
`R-D→R-H`, `R-H→ASSEMBLY`. Everything else raises `TransitionError`
before execution. Cross-experiment lineage reuse is rejected.

## 3. N-H sealing and information flow

Phase A executes N-D and N-H on separate fresh agent instances, seals
N-H (`SealedBaseline`: scope, scope/scope-fingerprint,
baseline fingerprint, payload, seal fingerprint, release flag), then
discards execution objects. Phase B/C/D signatures have no sealed
parameter — held-out contents cannot arrive, structurally. Release
happens exactly once, only with phase `"assembly"`, after verifying
`fingerprint(payload) == seal_fingerprint`; double release, wrong
phase, or tampering fails closed. R-H requires scope equality with
the seal (window, universe, costs, cash, PIT/vintage, env
fingerprint); only agent lineage may differ.

## 4. Configuration and identity

Production configs come from `benchmarks/manifest.yaml` and fail
closed on any mismatch (window, universe, costs, cash, pool,
sequence, budgets, benchmark entry) — no defaults, no normalisation.
Experiment identity is SHA-256 over canonical JSON of the closed
scientific field set (identity.py); wall-clock/UUID/PID/hostname
cannot enter (no such parameters exist). Arm identities derive
deterministically.

## 5. Preflight (dry run, zero episodes)

`preflight()` verifies manifest match, E3-D file fingerprint,
environment/benchmark/agent fingerprints, agent lifecycle
(importable, identity match, reset/act callable), window
non-overlap, scope well-formedness, budget coverage
(tests≥sequence, repairs≥1, runs≥3), arm identities, artefact path.
`ensure_preflight()` fails closed listing every failed check.

## 6. Result persistence and reproduction

`ExperimentResult` (frozen; unknown JSON fields rejected) carries
identities, configuration, lineage, four metric vectors, both paired
deltas (RQ3 names `baseline_original_heldout`/`repaired_heldout`
explicitly), the RQ4 descriptive vector with status
`DESCRIPTIVE_ONLY_SINGLE_HYPOTHESIS`, failure state, integrity
checks, and fingerprints; scientific identity excludes the
operational block. Saved to `results/e3/<experiment_id>.json`.
Reproduction rebuilds from the persisted file and compares
fingerprints, labelled REPRODUCTION — never independent replication.

## 7. RQ capture summary

RQ1: E2 artefact references (hypotheses → traces → fingerprints),
plus a pinned `diagnostic_state_snapshot` in `arm_records`
(hypothesis id/status/confidence, hypothesis updates, stopping
reason, open-hypothesis ids) so future Tier-1 artefacts carry
independently verifiable resolution evidence. The snapshot is a
read-only passthrough of the completed DiagnosticState using
existing deterministic serialisation; the frozen E3-D resolution
criterion itself is unchanged.
RQ2: matched N-D/R-D full 25-metric vectors + Δturnover pairing data.
RQ3: N-D/N-H/R-D/R-H vectors + Δdiagnostic/Δheldout with named
comparators. RQ4: descriptive vector only; any "discrimination"
labelling is a test-failing offence.

## 8. Failure semantics and Tier boundary

E2/E3-D states flow through unchanged (SUCCESS/INCONCLUSIVE/
REGRESSION/INVALID/FAILED; FAILED≠REJECTED; INVALID≠bad agent).
`ProtocolAmbiguityError` fires on any unfrozen scientific choice.
No p-values, CIs, tests, effect sizes, or multiplicity anywhere —
verified by source scan (no scipy/statsmodels/sklearn/stats
imports). Statistics belong downstream.

## 9. Operator workflow

1. Build config from manifest. 2. Call `run_experiment()` — the
   single canonical entrypoint composing verify → transcription →
   preflight → identity → A → B → C → D → E → persist → return.
   Fix failures (config or manifest process — never weaken checks).
3. Execute phases A→E sequentially, one campaign at a time (no
   parallel environments; ~15 serial env constructions per campaign
   is the accepted operational cost — isolation is never traded for
   speed). 4. Verify result fingerprint. 5. Reproduce from artefact
   file. Tier-1 market execution itself is a later milestone gated
   on this harness passing review, not part of the build.

## 10. Original-agent ownership

N-D, N-H, diagnosis, and repair each receive a separate fresh
instance from the canonical benchmark identity, reset before use;
no instance is shared across arms. The diagnosis instance is
discarded after Phase B; repair receives a fresh equivalent
instance. Legitimacy is determinism + reset-state equivalence
(fingerprint-equal fresh instances), not object identity — proven
by the mocked campaign test, which also proves the repair object
is never the diagnosis object. Transcription (`verify_transcription`
in `lifecycle.py`) is checked before any executable identity is
derived and fails closed on hypothesis/pool/metric/descriptor
mismatch.
