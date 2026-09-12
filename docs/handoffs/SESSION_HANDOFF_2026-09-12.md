# Research Session Handoff — 2026-09-12

Repository: `PhantomBeast2090/Adaptive_Agentic_Evaluation_and_Repair_of_Autonomous_Trading_Agents`
Branch: `main`
HEAD at handoff creation: `dcab5ea7978cae6cdb3e3ffc82cbb627c9afbcd6` (== `origin/main`, verified via `git ls-remote`)
Working tree: clean apart from known pre-existing artifacts (`data/raw/convfinqa/source`, `data/raw/finqa/source` submodule contents, `data/raw/india/fixed_income/.DS_Store` — never commit these).
Implementation root: `agentic-finance-evaluation/`. Last full suite: **448 passed, 0 failed** (run 2026-09-12).

## 1. Research objective and philosophy

Central objective: evaluate autonomous trading agents using historical information sets **without hindsight leakage**. The project builds an adaptive agentic evaluation-and-repair loop; Indian multi-asset data is the evaluation substrate, not the contribution.

Non-negotiable ranking (applies to every milestone, including Brent):

- DATA AVAILABILITY > DATA COMPLETENESS
- SOURCE PROVENANCE > CONVENIENCE
- EXPLICIT UNKNOWN > FABRICATED TIMESTAMP
- PRESERVING REVISIONS > SILENTLY OVERWRITING HISTORY
- FAIL-CLOSED > LEAKAGE

Do not optimize for the largest dataset. Optimize for defensible historical information boundaries. A smaller, blocked, provenance-tracked dataset beats a larger one built on assumptions.

## 2. Frozen architecture (reuse, do not redesign)

- `src/india/information_set.py` — `InformationSet(vintages, allow_pre_observation=...)`; availability `<= t`, latest eligible vintage per variable/period; raises on missing availability (fail-closed inputs expected to be pre-filtered).
- `src/india/manifest.py` — `ManifestManager`; SHA-256 raw/processed hashing; multi-file `raw_paths`/`raw_artifacts`; `validate_manifest()` must return `[]`.
- `src/india/leakage_audit.py` — `LeakageAuditor().audit_all(price_df=...)`; `is_clean` required.
- `src/india/coverage_audit.py`, `calendar.py`, `quality_gate.py` — shared validation.
- Canonicalizers: `nifty_canonicalize.py`, `nifty500_canonicalize.py`, `vix_canonicalize.py`, `usdinr_canonicalize.py`, `gsec_canonicalize.py`, `tbill_canonicalize.py` (tenor-parameterized 91D/364D), `gold_canonicalize.py`, `policy_canonicalize.py` (agent gate + `AGENT_ELIGIBLE_STATUSES`), `cpi_canonicalize.py`, `iip_canonicalize.py`.
- Schemas: `src/schemas/india_data.py` (`IndianMacroRecord` carries `observation_date` + `availability_date` + `revision_version`; availability must not precede observation for retrospective macro).
- Data contract: `agentic-finance-evaluation/INDIAN_DATA_CONTRACT.md`. Inventory: `INDIAN_DATA_SOURCE_INVENTORY.md`. Coverage: `INDIAN_DATA_COVERAGE_AUDIT.md` (regenerated via `PYTHONPATH=. python3 scripts/audit_indian_data_coverage.py`).
- Tests: `tests/india/test_<dataset>_canonical.py` (~25 focused tests each: targeting, schema, numeric, chronology, provenance, SHA, leakage 6-case pattern, blocked eligibility, bookkeeping). Never weaken existing tests.
- Config: `configs/india_data.yaml` (`required_datasets` includes `crude_oil_brent_daily`, still pending).

## 3. Completed datasets (all manifest-verified 2026-09-12; ALL `acquired/passed/BLOCKED`)

| Dataset | Rows / coverage | Manifest → processed |
|---|---|---|
| NIFTY 50 (NSE daily) | 7183, 1997-11-03→2026-09-11 | `nse_nifty_50_daily.yaml` → `market/nse_nifty_50_daily.csv` |
| NIFTY 500 (NSE daily) | 7413, 1996-11-04→2026-09-11 | `nse_nifty_500_daily.yaml` → `market/nse_nifty_500_daily.csv` |
| India VIX (NSE daily) | 4004, 2010-07-19→2026-09-11 | `nse_india_vix_daily.yaml` → `market/nse_india_vix_daily.csv` |
| USD/INR (RBI ref, daily) | 5878, 1998-08-25→2026-09-11 | `rbi_usd_inr_daily.yaml` → `market/rbi_usd_inr_daily.csv` |
| 10Y G-Sec (RBI weekly) | 465 Fridays, 2017-10-13→2026-09-04 | `rbi_gsec_10y_yield.yaml` → `market/rbi_gsec_10y_weekly.csv` |
| 91D T-Bill (RBI weekly) | 458 (7 `-` placeholders excluded), same Fridays | `rbi_gsec_91d_yield.yaml` → `market/rbi_tbill_91d_weekly.csv` |
| 364D T-Bill (RBI weekly) | 459 (6 `-` placeholders excluded), same Fridays | `rbi_gsec_364d_yield.yaml` → `market/rbi_tbill_364d_weekly.csv` |
| RBI policy rates (event) | 187 events / 62 decision groups, 2008-06-12→2025-12-05 | `rbi_policy_rate_events.yaml` → `macro/rbi_policy_rate_events.csv` |
| MCX Gold futures (contract-level, NO continuous series/roll) | 29646 rows, 6353 trade dates, 2003-11-10→2026-09-11 | `mcx_gold_futures_individual_contracts.yaml` → `instruments/mcx_gold_futures_individual_contracts.csv` |
| CPI (MoSPI, §4) | 209 rows / 156 months, 2013-01→2025-12 | `mospi_cpi_combined_monthly.yaml` → `macro/mospi_cpi_combined_monthly.csv` |
| IIP (MoSPI, §5) | 345 rows / 168 months, 2012-04→2026-03 | `mospi_iip_general_monthly.yaml` → `macro/mospi_iip_general_monthly.csv` |

Raw locations: `data/raw/india/{indices,india_vix,currency,fixed_income/50 Macroeconomic Indicators.xlsx,macro/policy+handbook,gold/,macro/cpi/ (111 files),macro/iip/ (132 files)}`. Raw is immutable; processed files carry their own SHA-256.

Key anomalies already documented in manifests (do not relitigate): RBI workbook shared across 10Y/91D/364D (same SHA); policy dual-source (Handbook Table 40 + 61 evidence files; 27 pre-2016 unverified events agent-ineligible via `build_agent_information_set`); gold stays contract-level (roll deferred); USD/INR 2018–2022 source gap never filled.

## 4. CPI state (CLOSED, verified against manifest — do not touch)

MoSPI/NSO All-India CPI Combined General index, base 2012=100, **index-only** (`cpi_index`), 2013-01→2025-12, 156 periods, **209 rows = 82 provisional + 82 final + 2 imputed (COVID) + 23 revision_back_series (2013-01..2014-11 @ 2015-02-12 revision release) + 20 final_series_only (NULL availability, agent-ineligible)**. Genuine revisions preserved (e.g. Jan-2025 193.5→193.4); Mar-2020 final never published (prov retained, documented). 136/156 months verified release timing. Leakage suite green. `acquired/passed/BLOCKED`. Canonical SHA `8e31219a…` (full value in manifest).

## 5. IIP state (CLOSED, verified against manifest — do not touch)

MoSPI/NSO All-India IIP General Index level, base 2011-12=100, **index-only** (`iip_index`), 2012-04→2026-03, 168 consecutive months, **345 rows = 89 quick + 70 first_revision + 81 final + 60 back_series (@2017-05-12) + 45 republished**. Arithmetic: **89 + 70 + 81 + 60 + 45 = 345**. Vintage model is empirical per release (classic QE/R1(M−1)/Final(M−3); new-format 2025+ finals M−1, sometimes M−1..M−3). COVID Apr-2020 56.3→53.6→54.0 preserved as stated with non-comparability notes. 168/168 months verified availability; 10 named-but-unvalued early-2017 revisions preserved without fabrication. RBI corroboration: exact match Oct-2017..Mar-2023, unexplained RBI-side rescaling after (direction corr 0.98) — MoSPI-direct canonical stands, RBI never used for values. Canonical SHA `ebf24b19…`. `acquired/passed/BLOCKED`.

## 6. Most recent commit (surgical correction, implementation untouched)

`dcab5ea7978cae6cdb3e3ffc82cbb627c9afbcd6` — "Correct IIP milestone republished vintage count". Changed exactly one token in `INDIAN_DATA_SOURCE_INVENTORY.md`: `46 republished` → `45 republished`. Manifest, tests, commit `a5b3ca0` message, and CSV already said 45; the correction aligned documentation with the correct repository state. Nothing else changed.

## 7. Coverage state

Pending mandatory datasets: **`crude_oil_brent_daily`** (`pending_manual_download`, `acquisition_pending`, tier C, variable `CRUDE_BRENT_USD_DAILY`, institution `FRED_EIA`) and **`nse_equity_bhavcopy_daily`** (same pending state). Raw dirs `data/raw/india/{breadth,crude,equities}/` exist as placeholders.
Project blockers (unchanged, must remain): (1) historical Indian trading calendar, (2) common temporal intersection. Dataset-level validation ≠ experiment readiness — no dataset is experiment-eligible and none may be marked so in this milestone.

## 8. Next objective: EIA Brent Spot Daily (from scratch)

Acquire and validate **EIA Europe Brent Spot Price FOB**, series **`RBRTE`**, official source `https://www.eia.gov/dnav/pet/hist/RBRTED.htm`, into dataset `crude_oil_brent_daily`, reusing §2 architecture end-to-end (acquire → immutable raw + SHA → deterministic canonicalize → validate → availability → leakage tests → cross-validation → manifest → focused tests → inventory/coverage → commit + push + evidence report).

## 9. Brent methodological contract (locked)

- Brent is GLOBAL EXOGENOUS INPUT (tier C/crude), not an Indian exchange instrument.
- Use Europe Brent Spot Price FOB (RBRTE). NOT Brent futures. Never convert spot↔futures. No OHLC from another source. No Yahoo/Investing/Kaggle substitution.
- No filling weekends/holidays/source gaps; no interpolation. Brent's calendar must NOT be forced onto NSE (reconciliation belongs to the later intersection layer).
- Canonical variable: `brent_spot_usd_bbl`. Keep `observation_date` vs `availability_date` distinct. If EIA lacks historical publication timestamps: do not invent them — preserve the limitation and fail closed in the information gate.
- Expected final state: ACQUIRED + VALIDATED + VALIDATED_BUT_BLOCKED (global blockers remain).

## 10. Brent implementation plan

1. Inspect `src/india/` canonicalizers (esp. CPI/IIP), manifests, information gate. 2. Fetch official EIA RBRTE artifact (record URL, timestamp, bytes, SHA). 3. Preserve raw immutably under `data/raw/india/crude/`. 4. Write narrow `src/india/brent_canonicalize.py` (no redesign). 5. Canonicalize deterministically to `data/processed/india/macro/` (naming per existing conventions). 6. Validate schema/dates/duplicates/conflicts/numerics/missingness/calendar/chronology. 7. Resolve availability semantics (fail closed if unknown). 8. Leakage tests (6-case pattern). 9. Secondary-source cross-validation (document agreement/limits; never overwrite). 10. Write `crude_oil_brent_daily.yaml` manifest (full provenance, blockers, limitations). 11. Add `tests/india/test_brent_canonical.py`. 12. Update inventory + regenerate coverage audit. 13. Full suite green. 14. Verify SHAs + `git diff` scope. 15. Single commit + push. 16. Evidence report. Never declare success on download alone.

## 11. Brent validation questions (must answer explicitly)

Exact artifact? RBRTE definition? First/last observation? Row/unique-date counts? Duplicates? Conflicts? Malformed/non-finite/nonpositive values? Gaps — which are normal calendar (weekends/holidays) vs anomalies? Are weekends/holidays represented? Historical availability dates or fail-closed treatment? Revisions/vintages? Secondary-source agreement? Remaining limitations?

## 12. Must NOT do

Redo CPI/IIP; change IIP counts/methodology; modify frozen canonicals without defect evidence; third-party substitution; filling/interpolation; fabricated timestamps; silent conflict resolution; marking anything experiment-ready; removing BLOCKED; solving calendar/intersection inside Brent.

## 13. Verification ritual (run before any milestone commit)

`git status` clean (excl. known artifacts) → full suite green → `ManifestManager.validate_manifest` empty for all datasets → recompute every raw/processed SHA vs manifest → `git diff` scope-checked → single focused commit → push → `ls-remote` sync check.
