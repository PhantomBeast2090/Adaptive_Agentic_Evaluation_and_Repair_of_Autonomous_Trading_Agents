# Indian Data Coverage Audit

> Generated from acquired artifacts and manifests. This report does not
> freeze context, discovery, re-evaluation, or OOD experiment dates.

## 1. Acquisition status

- Acquired and auditable datasets: **1**
- Acquired mandatory market/macro datasets: **0**
- Acquired support/calendar artifacts: **1**
- Pending/unavailable datasets: **13**
- Artifact read errors: **0**
- Pending datasets:
  - `crude_oil_brent_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `mcx_gold_futures_individual_contracts`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `mospi_cpi_combined_monthly`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `mospi_iip_general_monthly`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `nse_equity_bhavcopy_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `nse_india_vix_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `nse_nifty_500_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `nse_nifty_50_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `rbi_gsec_10y_yield`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `rbi_gsec_364d_yield`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `rbi_gsec_91d_yield`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `rbi_policy_rate_events`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `rbi_usd_inr_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.

## 2. Dataset-by-dataset coverage

- Source: `NSE`
- Raw SHA-256: `933cf5dc6dd4efe3b8db8ce6ecd6ecb2582929f5e0b4faffdb88e11cf4efdfbe`
### `nse_trading_holidays_2026`
- Earliest: `2026-01-01`
- Latest: `2026-12-25`
- Observations: 239
- Unique dates: 25
- Duplicate timestamps: not applicable (category membership)
- Duplicate identifier pairs: 0
- Temporal gaps above threshold: 17
- Note: Repeated dates are evaluated with identifier columns; date repetition alone is not treated as a duplicate record.
- Note: WARNING: Timestamps are not monotonically increasing.
- Note: INFO: 17 gap(s) detected. First: (datetime.date(2026, 1, 1), datetime.date(2026, 1, 15))
- Note: Repeated dates are legitimate market-segment membership; duplicate records are evaluated by `(market_segment, trading_date)`.

## 3. Missingness

Missingness is reported per required field above. No values were forward-filled by this audit.

## 4. Duplicate analysis

Duplicate timestamps and date/identifier pairs are reported per dataset above.

## 5. Calendar analysis

Trading-day checks use the versioned NSE holiday artifact when its coverage includes the audited years. Years outside that artifact are reported as calendar-unavailable rather than inferred from weekdays.

## 6. Information-availability analysis

Macro and policy datasets must carry observation_date and availability_date. Values are not eligible for agent observations before availability_date.

## 7. Common intersection

- Earliest common usable date: `not computable`
- Latest common usable date: `not computable`
- Calendar duration: 0 days
- Datasets included: none
- Datasets excluded: nse_trading_holidays_2026
- Jointly usable sessions: 0
- Limiting datasets: none
- Exclusion reasons:
  - `nse_trading_holidays_2026`: Coverage too short: 25 usable sessions < min 365 (2026-01-01 to 2026-12-25).

## 8. Data-quality blockers

- No artifact read errors were encountered.

## 9. Leakage findings

- Confirmed leaks: 0
- Potential leaks: 0
- Mitigated issues: 0
- Unresolved issues: 0
- Gold futures must remain contract-level until a roll method is selected and independently audited.

## 10. Recommended next methodological decision

Complete official-source acquisition and release-date verification for the mandatory datasets. Then review this audit to define the longest clean common period before selecting any temporal split boundaries.
