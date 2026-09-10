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
  - `mcx_gold_futures_individual_contracts`: pending_manual_download — [mcx_gold_futures_individual_contracts] Acquisition from MCX Historical Data failed: No MCX gold futures CSV files found in data/raw/india/gold/. MCX requires individual contract downloads per month/year via their website. Automated bulk download is not available without a data vendor subscription.

Manual download instructions:

MCX Gold Futures Manual Download Instructions:

For EACH contract month:
1. Visit: https://www.mcxindia.com/market-data/historical-data
2. Select: Commodity = GOLD (or GOLDM for mini)
3. In the contract dropdown, select a specific month/year
4. Set date range = contract full trading period
5. Click "Get Data" → Download as CSV
6. Name the file: mcx_gold_<CONTRACTSYMBOL>.csv
   Example: mcx_gold_GOLDFEB2024.csv
7. Place at: data/raw/india/gold/

Repeat for all contracts in the desired history window.

For bulk historical data (alternative):
  MCX data vendor services may provide bulk downloads.
  Quantsapp, Traders Carnival, NSE Data Analytics may have MCX data.
  If using a secondary source, document it in the manifest.

Expected CSV columns per file:
  Date | Open | High | Low | Close | Volume | Open Interest | Value (Lakhs)
  [optional: Expiry Date | Contract Symbol]

IMPORTANT: Each file = one contract. Do NOT manually concatenate contracts.
The roll methodology will be designed separately after coverage audit.

  - `mospi_cpi_combined_monthly`: pending_manual_download — [mospi_cpi_combined_monthly] Acquisition from MoSPI CPI / mospi.gov.in failed: MoSPI CPI data requires web download from mospi.gov.in. Automated download is not reliably possible. Release dates (critical for information availability) require separate collection from press release archives.

Manual download instructions:

MoSPI CPI Manual Download:
1. Visit: https://mospi.gov.in/consumer-price-indices-cpi
2. Download the "CPI Data" historical table (Excel or CSV)
3. Place at: data/raw/india/macro/cpi_combined.csv

For release dates (CRITICAL for information availability):
1. Visit: https://mospi.gov.in/press-release-consumer-price-index
2. Extract the date each month's CPI was released
3. Or use: https://www.rbi.org.in/scripts/Bs_PressReleaseDisplay.aspx
   (filter by CPI press releases)
4. Create a CSV with columns: reference_month, release_date
   reference_month format: YYYY-MM (e.g. 2024-01 for January 2024)
   release_date format: YYYY-MM-DD
5. Place at: data/raw/india/macro/cpi_release_dates.csv

Alternative automated source (secondary):
  RBI DBIE also carries CPI data:
  https://dbie.rbi.org.in/ → Price and Monetary → Consumer Price Index
  HOWEVER: DBIE may not include individual release dates.
  Use MoSPI as the primary source.

Expected CPI CSV structure:
  Month/Year | CPI_Combined (General) | CPI_Urban | CPI_Rural | ...
  OR: Month | Year | CPI | [sub-indices]
  Base year: 2012=100 for the new series

  - `mospi_iip_general_monthly`: pending_manual_download — [mospi_iip_general_monthly] Acquisition from MoSPI IIP / mospi.gov.in failed: MoSPI IIP data requires web download. Release dates (critical for information availability) require separate collection.

Manual download instructions:

MoSPI IIP Manual Download:
1. Visit: https://mospi.gov.in/index-industrial-production
2. Download historical IIP data (Excel or CSV)
3. Place at: data/raw/india/macro/iip_general.csv

For release dates (CRITICAL for information availability):
1. Visit MoSPI press releases or IIP release calendar
2. Record the date each month's IIP was first released
3. Create: data/raw/india/macro/iip_release_dates.csv
   Columns: reference_month (YYYY-MM), release_date (YYYY-MM-DD)

Alternative source:
  RBI DBIE: https://dbie.rbi.org.in/
  Navigate: Real Economy → Industry → IIP

Expected IIP CSV structure:
  Month/Year | General | Mining | Manufacturing | Electricity
  Base year: 2011-12=100 (current series)

  - `nse_equity_bhavcopy_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `nse_india_vix_daily`: pending_manual_download — [nse_india_vix_daily] Acquisition from https://www.nseindia.com/market-data/india-vix failed: Automated NSE VIX fetch failed: NSE base page returned 403. NSE website requires session authentication that is not reliably automated. Manual download required.

Manual download instructions:

India VIX Manual Download Instructions:
1. Visit: https://www.nseindia.com/market-data/india-vix
2. Click "Historical Data" tab
3. Select the widest available date range
4. Download as CSV
5. Place the file at:
   data/raw/india/india_vix/india_vix_daily.csv

Expected columns (NSE VIX CSV):
  Date | Open | High | Low | Close | Previous Close | Change | % Change

Note: India VIX history starts approximately from 2008-11-02.

  - `nse_nifty_500_daily`: pending_manual_download — [nse_nifty_500_daily] Acquisition from NSE historical data for NIFTY 500 failed: Automated NSE index download requires session authentication not reliably automatable via HTTP. Manual download required.

Manual download instructions:

NSE Index 'NIFTY 500' Manual Download Instructions:
1. Visit: https://www.nseindia.com/market-data/historical-index-data
2. In the "Select Index" dropdown, choose: NIFTY 500
3. In "From Date" enter the earliest available date
4. In "To Date" enter today's date
5. Click "Get Data", then "Download CSV"
6. Place the downloaded file at:
   data/raw/india/indices/nifty_500_daily.csv

Expected columns (NSE format):
  Date | Open | High | Low | Close | Shares Traded | Turnover (Rs. Cr)

Note: NSE historical index data typically starts from:
  NIFTY 50: ~1999-01-04
  NIFTY 500: ~1995-01-01
  NIFTY BANK: ~2000-01-04
  NIFTY IT, PHARMA, etc.: varies

  - `nse_nifty_50_daily`: pending_manual_download — [nse_nifty_50_daily] Acquisition from NSE historical data for NIFTY 50 failed: Automated NSE index download requires session authentication not reliably automatable via HTTP. Manual download required.

Manual download instructions:

NSE Index 'NIFTY 50' Manual Download Instructions:
1. Visit: https://www.nseindia.com/market-data/historical-index-data
2. In the "Select Index" dropdown, choose: NIFTY 50
3. In "From Date" enter the earliest available date
4. In "To Date" enter today's date
5. Click "Get Data", then "Download CSV"
6. Place the downloaded file at:
   data/raw/india/indices/nifty_50_daily.csv

Expected columns (NSE format):
  Date | Open | High | Low | Close | Shares Traded | Turnover (Rs. Cr)

Note: NSE historical index data typically starts from:
  NIFTY 50: ~1999-01-04
  NIFTY 500: ~1995-01-01
  NIFTY BANK: ~2000-01-04
  NIFTY IT, PHARMA, etc.: varies

  - `rbi_gsec_10y_yield`: pending_manual_download — [rbi_gsec_10y_yield] Acquisition from RBI DBIE (10Y yield) failed: DBIE automated fetch failed: HTTPSConnectionPool(host='dbie.rbi.org.in', port=443): Max retries exceeded with url: /DBIE/dbie.rbi?site=export&seriesId=BSR1:BISQ:A:A:4:0:WT.GSEC_10Y&format=CSV (Caused by SSLError(SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'dbie.rbi.org.in'. (_ssl.c:1081)"))). RBI DBIE requires authenticated session or API key. Manual download required.

Manual download instructions:

RBI/DBIE 10Y Yield Manual Download:
1. Visit: https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
2. Navigate: Financial Markets → Government Securities Market (or Money Market for T-Bills)
3. Find series for 10Y yield/rate
4. Select maximum date range
5. Download as CSV
6. Place at: data/raw/india/fixed_income/gsec_10y_yield.csv

Alternative (FBIL):
  https://www.fbil.org.in/#/home  → Benchmark Rates → FBIL T-Bill Rates
  (For T-Bills only; G-Sec rates remain from RBI/DBIE)

Expected CSV columns:
  Date | Yield (%) | [optional: Price, Security ID]

  - `rbi_gsec_364d_yield`: pending_manual_download — [rbi_gsec_364d_yield] Acquisition from RBI DBIE (364D yield) failed: DBIE automated fetch failed: HTTPSConnectionPool(host='dbie.rbi.org.in', port=443): Max retries exceeded with url: /DBIE/dbie.rbi?site=export&seriesId=BSR1:BISQ:A:A:4:0:WT.TBILL_364D&format=CSV (Caused by SSLError(SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'dbie.rbi.org.in'. (_ssl.c:1081)"))). RBI DBIE requires authenticated session or API key. Manual download required.

Manual download instructions:

RBI/DBIE 364D Yield Manual Download:
1. Visit: https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
2. Navigate: Financial Markets → Government Securities Market (or Money Market for T-Bills)
3. Find series for 364D yield/rate
4. Select maximum date range
5. Download as CSV
6. Place at: data/raw/india/fixed_income/tbill_364d.csv

Alternative (FBIL):
  https://www.fbil.org.in/#/home  → Benchmark Rates → FBIL T-Bill Rates
  (For T-Bills only; G-Sec rates remain from RBI/DBIE)

Expected CSV columns:
  Date | Yield (%) | [optional: Price, Security ID]

  - `rbi_gsec_91d_yield`: pending_manual_download — [rbi_gsec_91d_yield] Acquisition from RBI DBIE (91D yield) failed: DBIE automated fetch failed: HTTPSConnectionPool(host='dbie.rbi.org.in', port=443): Max retries exceeded with url: /DBIE/dbie.rbi?site=export&seriesId=BSR1:BISQ:A:A:4:0:WT.TBILL_91D&format=CSV (Caused by SSLError(SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'dbie.rbi.org.in'. (_ssl.c:1081)"))). RBI DBIE requires authenticated session or API key. Manual download required.

Manual download instructions:

RBI/DBIE 91D Yield Manual Download:
1. Visit: https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
2. Navigate: Financial Markets → Government Securities Market (or Money Market for T-Bills)
3. Find series for 91D yield/rate
4. Select maximum date range
5. Download as CSV
6. Place at: data/raw/india/fixed_income/tbill_91d.csv

Alternative (FBIL):
  https://www.fbil.org.in/#/home  → Benchmark Rates → FBIL T-Bill Rates
  (For T-Bills only; G-Sec rates remain from RBI/DBIE)

Expected CSV columns:
  Date | Yield (%) | [optional: Price, Security ID]

  - `rbi_policy_rate_events`: pending_manual_download — [rbi_policy_rate_events] Acquisition from RBI DBIE / RBI website failed: RBI policy rate data requires web navigation through DBIE. Manual download is required to ensure accurate announcement dates are captured (not just effective dates).

Manual download instructions:

RBI Policy Rate Manual Download:

Option A — RBI DBIE (preferred):
  1. Visit: https://dbie.rbi.org.in/
  2. Navigate: Financial Sector → Monetary Policy → Key Policy Rates
  3. Select: Repo Rate (and optionally: Reverse Repo, MSF Rate, CRR, SLR)
  4. Download as CSV
  5. Place at: data/raw/india/macro/rbi_policy_rate.csv

Option B — RBI Handbook of Statistics:
  1. Visit: https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+Economy
  2. Find the monetary policy table
  3. Download relevant tables

CRITICAL: Each record must include:
  - effective_date (when rate took effect)
  - announcement_date (when RBI published the decision)
  - rate_type (e.g. REPO, REVERSE_REPO, MSF)
  - rate_pct (rate in percentage, e.g. 6.5)
  - [optional] stance (accommodative, neutral, withdrawal of accommodation)

If the source only provides effective dates, record both effective_date and
announcement_date as the same value and flag in notes that announcement dates
were not separately captured.

  - `rbi_usd_inr_daily`: pending_manual_download — [rbi_usd_inr_daily] Acquisition from RBI Reference Rate Archive / FBIL failed: RBI Reference Rate Archive requires web form interaction not reliably automatable. FBIL may require API key. Manual download required.

Manual download instructions:

USD/INR Official Rate Manual Download:

Option A — RBI Reference Rate Archive (preferred):
  1. Visit: https://www.rbi.org.in/scripts/ReferenceRateArchive.aspx
  2. Select the widest available date range
  3. Click "Get Data" then download/export
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

Option B — FBIL USD/INR:
  1. Visit: https://www.fbil.org.in/#/home
  2. Navigate to Benchmark Rates → Reference Rates
  3. Download USD/INR Reference Rate historical data
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

Option C — RBI DBIE:
  1. Visit: https://dbie.rbi.org.in/
  2. Navigate: External Sector → Exchange Rates → Spot Rate (USD/INR)
  3. Download as CSV
  4. Place at: data/raw/india/currency/usd_inr_daily.csv

Expected minimum columns:
  Date | USD/INR (INR per 1 USD)

Note: This MUST be the official RBI/FBIL reference rate.
Do NOT use retail/commercial bank rates or Yahoo Finance as primary source.


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

- Status: **INCOMPLETE_DATASET_SET**
- Earliest common usable date: `not computable`
- Latest common usable date: `not computable`
- Calendar duration: 0 days
- Datasets included: none
- Datasets excluded: mcx_gold_futures_individual_contracts, mospi_cpi_combined_monthly, mospi_iip_general_monthly, nse_india_vix_daily, nse_nifty_500_daily, nse_nifty_50_daily, rbi_gsec_10y_yield, rbi_gsec_364d_yield, rbi_gsec_91d_yield, rbi_policy_rate_events, rbi_usd_inr_daily
- Jointly usable sessions: 0
- Limiting datasets: none
- Exclusion reasons:
  - `mcx_gold_futures_individual_contracts`: Dataset not audited — no coverage data available.
  - `mospi_cpi_combined_monthly`: Dataset not audited — no coverage data available.
  - `mospi_iip_general_monthly`: Dataset not audited — no coverage data available.
  - `nse_india_vix_daily`: Dataset not audited — no coverage data available.
  - `nse_nifty_500_daily`: Dataset not audited — no coverage data available.
  - `nse_nifty_50_daily`: Dataset not audited — no coverage data available.
  - `rbi_gsec_10y_yield`: Dataset not audited — no coverage data available.
  - `rbi_gsec_364d_yield`: Dataset not audited — no coverage data available.
  - `rbi_gsec_91d_yield`: Dataset not audited — no coverage data available.
  - `rbi_policy_rate_events`: Dataset not audited — no coverage data available.
  - `rbi_usd_inr_daily`: Dataset not audited — no coverage data available.

## 8. Data-quality blockers

- No artifact read errors were encountered.

## 9. Leakage findings

- Leakage validation status: **NOT_EVALUABLE**
- Datasets checked: none
- Confirmed leaks: 0
- Potential leaks: 0
- Mitigated issues: 0
- Unresolved issues: 0
- Gold futures must remain contract-level until a roll method is selected and independently audited.

## 10. Recommended next methodological decision

Complete official-source acquisition and release-date verification for the mandatory datasets. Then review this audit to define the longest clean common period before selecting any temporal split boundaries.
