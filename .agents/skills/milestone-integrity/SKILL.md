---
name: milestone-integrity
description: Gate every change against the frozen registry (Indian env 5eb82b1, E0 8432a26, E1 6bc678d, E2-A fa0d87d, E2-B ad94c60, E2-C 8962485, E2-D 9365401, E2-E e9d8fbe). E2-F d254cad is ACTIVE, not frozen. Enforces preserve-vs-depend-vs-modify, surgical protocol, tiered verification. Invoke before any edit, commit, or push.
---

# Milestone Integrity

Dependency-free gate. This skill references no other project skill.

## 1. Frozen registry (exact SHAs — verify with `git rev-parse`)

| Milestone | Commit | Scope frozen |
|---|---|---|
| Indian environment | `5eb82b1` | Tradable universe, multi-asset env, calendars, PIT/vintage |
| E0 | `8432a26` | Evaluator contracts incl. immutable `EvaluationBudget` (`evaluation/contracts/`) |
| E1 | `6bc678d` | Deterministic baseline evaluator (`evaluation/baseline/`) |
| E2-A | `fa0d87d` | Diagnostic contracts incl. `DiagnosticState` (`evaluation/diagnostics/contracts/`) |
| E2-B | `ad94c60` | Diagnostic execution engine (`evaluation/diagnostics/execution/`) |
| E2-C | `8962485` | Hypothesis interpretation, directional-band v1 (`evaluation/diagnostics/interpretation/`) |
| E2-D | `9365401` | Adaptive selector (`evaluation/diagnostics/selection/`) |
| E2-E | `e9d8fbe` | Closed-loop orchestration (`evaluation/diagnostics/orchestration/`) |

**Active milestone (NOT frozen): E2-F at `d254cad`** ("Implement repair and independent validation").
E2-F contains two known budget-consumption blockers (repair units and validation-run
units are checked but not consumed). Never describe `d254cad` as frozen.

## 2. Frozen boundary semantics

- **Preserving** frozen contracts/semantics: mandatory for all work. Call frozen code
  through its public interfaces; assert against its documented behavior.
- **Depending on** frozen code: always allowed (e.g. E2-F calling E1 `run_baseline`,
  reading `EvaluationBudget`, using E0 `note_*` slots).
- **Modifying** frozen code: blocked by default. "Frozen" protects established
  contracts and semantics; it does not claim every line is untouchable under all
  conceivable explicitly-approved futures. For current work: E0–E2-E and
  `environment/`/`data/`/`configs/` are byte-untouchable; only E2-F
  (`evaluation/diagnostics/repair/`, `tests/diagnostics/repair/`,
  `docs/REPAIR_AND_VALIDATION.md`) may change.

## 3. Surgical-change protocol

Additive and local. Active-milestone files only. Implement → Harden commit pattern.
Milestone work ships as code + tests + docs triple. No ephemeral state: accounting
or provenance must be persistent, deterministic, serialisable, fingerprintable,
replayable — or it does not land. No hidden counters, module globals,
process-local state, wall-clock, UUID, PID, or randomness in identity paths.

## 4. Plan before implementation; refusal scripts

Milestone work requires an approved plan first. Refuse out-of-scope "improvements":
mutable `EvaluationBudget`, E0/E2-A contract edits, `DiagnosticState.from_dict`
surgery, weakening assertions to pass, return-threshold adjudication without
calibrated basis, Bayes/LLM/learning/search additions.

## 5. Verification order (tiered — full suite is NOT per-edit)

TARGETED TESTS → MILESTONE/FEATURE TESTS → RELEVANT REGRESSION CHUNKS →
FULL SUITE ONCE at milestone/release boundaries. Rationale: Indian-market
environment tests re-parse a ~1GB NSE CSV per episode; repeated full-suite runs
during development are wasteful, not rigorous.

## 6. Pre-commit gate

`git status --porcelain` + `git diff --stat <freeze-SHA>` must show only intended
active-milestone paths; read the diff through; then run the tier above.

## 7. Fenced global skill

`improve-codebase-architecture` conflicts with freeze discipline on frozen paths —
never apply it to E0–E2-E, `environment/`, `src/india/`, or manifests. Allowed
only on never-frozen code (active milestone internals, experiments, scripts).

## 8. Must NOT own

Market semantics (see `indian-market-integrity`), evaluation-loop semantics
(see `agentic-evaluation-loop`), statistical methodology.

## 9. Maintenance

Update this registry in the same commit as any future milestone freeze
(definition-of-done item). Annual stale-review otherwise.
