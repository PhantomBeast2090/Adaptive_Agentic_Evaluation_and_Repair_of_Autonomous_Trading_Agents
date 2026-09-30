# Reproducibility Guide

Frozen terminal state: `main` at the M-R8 + manuscript commits.
M-R8 is terminal — no M-R9 is authorised.

## 1. Environment

```bash
cd agentic-finance-evaluation
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Canonical Indian-market data is required under `data/processed/india/`
(NSE equities, India VIX, manifests under `data/manifests/india/`).
No network access is needed for any M-R6/M-R7/M-R8 rerun or test.

## 2. Rerunning the natural experiments

WARNING: reruns with `--overwrite` destroy the frozen artefacts they
reproduce. Copy `data/adaptive_repair/M-R{6,7,8}/` aside first, or run
without `--overwrite` (refuses if outputs exist, proving preservation).

```bash
cd agentic-finance-evaluation
./.venv/bin/python scripts/run_mr6.py --base-dir .
./.venv/bin/python scripts/run_mr6_controls.py
./.venv/bin/python scripts/run_mr7.py --base-dir .
./.venv/bin/python scripts/run_mr7_controls.py
./.venv/bin/python scripts/run_mr8.py --base-dir .
./.venv/bin/python scripts/run_mr8_controls.py
# M-R9: sequential, one experiment per invocation (CPU-bounded).
./.venv/bin/python scripts/run_mr9.py --base-dir . --only R9-A
./.venv/bin/python scripts/run_mr9.py --base-dir . --only R9-B
./.venv/bin/python scripts/run_mr9.py --base-dir . --only R9-C
./.venv/bin/python scripts/run_mr9.py --base-dir . --only R9-D
./.venv/bin/python scripts/run_mr9.py --base-dir . --only R9-E
./.venv/bin/python scripts/run_mr9.py --base-dir . --only R9-F
# Aggregate summary/tables/figures from frozen per-exp artefacts only.
./.venv/bin/python scripts/run_mr9.py --base-dir . --report-only
./.venv/bin/python scripts/run_mr9_controls.py
```

Expected verdicts: M-R6 NULL (0/9), M-R7 NULL×3 (0/9 each), M-R8 NULL
(0/9 under fixed N1). M-R8 depends on the frozen M-R6
`base_diagnostic.json` (reused, never rerun) — do not delete M-R6
artefacts before an M-R8 rerun.

Each run is heavy: every candidate triggers full-window Indian-env
baseline episodes (~1 GB NSE re-parse per episode). Allow ample time;
do not parallelise baseline episodes.

## 3. Tests (necessary chunks, low CPU)

```bash
cd agentic-finance-evaluation
# M-R8 + gate proofs (fast, no environment runs)
./.venv/bin/pytest tests/repair/test_mr8_conditional.py \
  tests/repair/test_mr8_protocol.py tests/repair/test_mr6_gates.py \
  tests/repair/test_mr7_normality.py tests/repair/test_mr7_protocol.py \
  tests/repair/test_mr6_natural.py -q
# Remainder of the repair suite (fast)
./.venv/bin/pytest tests/repair/ -q
# E2-F budget ledger
./.venv/bin/pytest tests/diagnostics/repair/test_budget_accounting.py -q
```

Reference state at freeze: repair suite + budget tests 130 passed
(M-R8); M-R9 adds 15 unit tests (protocol + activity/status proofs),
all passing. Campaign reference: 6/6 NULL, 44 candidates
(26 STATISTICAL_NULL, 18 SPECIFICITY_REJECT), 94 episodes.
The broader suite was intentionally not re-swept at freeze (CPU cost);
see paper §12.

## 4. Fingerprint reference

| Artefact | Fingerprint |
|---|---|
| M-R8 protocol | `8ebbe7ec96f9eebbb0c5783f6df6f998489f215e55ec43c4c0673a3b828e192a` |
| M-R8 trigger (`names_held > 2`) | `89aad28d5a9d3a9173febb24088245b40ce20cd3d2d60f32e53723ccd09249e7` |
| N1 normality (full) | `d46b518f4c83ec01e36fd08cfa362e79c9827419090c831230a16b06b59b3c37` (prefix `d46b518f4c83ec01`) |
| Shared policy (M-R6/M-R7/M-R8) | `db1a9a33f1df5dcd7a4ce1f3f23e555f48368ce23e7801c94d71b39b488ed203` |
| M-R8 manifest | `9da7172bda03e22364c85a09a5eecb6b15cfef3d1d9ac927bc21ea216e57672c` |

Verify with: recompute SHA-256 over sorted-keys compact JSON of the
corresponding `result.json` / `freeze.json` / `manifest.json` fields.

## 5. Frozen vs active paths

Frozen (byte-untouchable, verified zero-diff at freeze):
`data/adaptive_repair/M-R{6,7}/`, `configs/adaptive_repair/
mr6_natural.yaml`, `mr7_normality.yaml`, `evaluation/repair/
{natural,normality,adaptive,compiler,control_plane,gate}.py`,
`scripts/run_mr{6,7}.py`. M-R8 artefacts are frozen as of the M-R8
commit — treat `data/adaptive_repair/M-R8/` as immutable henceforth.

## 6. Submission contents

- Manuscript: `docs/PAPER.md` (with supplementary S1–S6).
- Experiment reports: `docs/M-R6_NATURAL_ADAPTIVE_REPAIR.md`,
  `docs/M-R7_NORMALITY_EXPERIMENT.md`,
  `docs/M-R8_CONDITIONAL_REPAIR.md`.
- Architecture: `docs/ADAPTIVE_REPAIR_ARCHITECTURE.md`.
- This guide: `docs/REPRODUCIBILITY.md`.
