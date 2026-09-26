# ML Model Licenses and Provenance (2026-09-26)

All models below are used strictly as evaluator-side diagnostic tools.
None is a contribution of this work. No weights are distributed with
this repository; weights download to the local Hugging Face cache
(`~/.cache/huggingface`, outside the repo) on first use and are never
committed.

## 1. Chronos-2 (foundation forecasting)

* Model: Chronos-2 (`Chronos2Pipeline`)
* Organisation: Amazon
* Identifier: `amazon/chronos-2`
* Checkpoint revision (resolved at runtime): `29ec3766d36d`
  (recorded per-run in `model_metadata` / manifest)
* Authorised fallback: `autogluon/chronos-2-small` (28M) — only on
  documented resource limits; `fallback_used` recorded in metadata.
  Not exercised in MLF-20260926 (full 120M ran; ~1.1 GB RSS).
* Licence: **Apache-2.0** (weights + `chronos-forecasting` package)
* Permitted research use: unrestricted including commercial; no
  additional obligations beyond licence text.
* Restrictions: none beyond Apache-2.0.
* Citation: Ansari et al., Chronos-2 technical report (2025),
  arXiv:2510.15821; Chronos, arXiv:2403.07815.
  https://huggingface.co/amazon/chronos-2
* Access requirements: none (public, unauthenticated download).
* Weights distributed with repo: NO.

## 2. TimesFM 3.0 (foundation forecasting)

* Model: TimesFM 3.0 PyTorch (`TimesFM3Forecaster`)
* Organisation: Google Research
* Identifier: `google/timesfm-3.0-pytorch`
* Checkpoint revision (resolved at runtime): `43046b85ec22`
  (recorded per-run)
* Licence: **TimesFM Non-Commercial License v1.0** (weights).
  Package source code (`timesfm==3.0.0`) is Apache-2.0; weights
  ≤2.5 remain Apache-2.0, but the 3.0 weights used here are
  non-commercial only.
* Permitted research use: non-commercial, non-production use only —
  testing, evaluation, academic research not tied to commercial gain,
  production deployment, or revenue generation. This project’s use
  (diagnostic evaluation of a research trading agent, no live
  trading, no commercial decision-making) falls within that scope.
* Restrictions: no commercial/production use; no redistribution of
  weights; derivatives inherit the restriction.
* Citation: Das et al., "A decoder-only foundation model for
  time-series forecasting", ICML 2024, arXiv:2310.10688.
  https://huggingface.co/google/timesfm-3.0-pytorch
* Access requirements: none observed (public download; HF rate-limit
  warning only).
* Weights distributed with repo: NO (1.32 GB stays in local HF cache).

## 3. TabPFN (tabular control — BLOCKED)

* Package `tabpfn==9.0.0`; weights `Prior-Labs/tabpfn_3_5` gated behind
  human Prior Labs licence acceptance + `TABPFN_TOKEN`. Unavailable in
  this environment; cells persist BLOCKED evidence. Not a negative
  result.

## 4. Classical controls (no external weights)

* Logistic Regression, HistGradientBoostingClassifier: scikit-learn
  1.9.0 (BSD-3-Clause). No checkpoints, no downloads.
