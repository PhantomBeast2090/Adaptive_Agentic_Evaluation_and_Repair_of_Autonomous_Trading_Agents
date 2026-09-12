# Indian Data Coverage Audit

> Generated from acquired artifacts and manifests. This report does not
> freeze context, discovery, re-evaluation, or OOD experiment dates.

## 1. Acquisition status

- Acquired and auditable datasets: **7**
- Acquired mandatory market/macro datasets: **6**
- Acquired support/calendar artifacts: **1**
- Pending/unavailable datasets: **7**
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


## 2. Dataset-by-dataset coverage

- Source: `NSE`
- Raw artifacts: `17 annual files`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2009-to-03-11-2010.csv`: `7601fd2bdff590ab7f01fdb0458d3b141747325c8a094339151837e5ea4a32c1`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2010-to-03-11-2011.csv`: `2ad584779d4a6f95d847d2ce078d1db7169d33107ac0ba5a277bb9f47390992c`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2011-to-03-11-2012.csv`: `212310ce97cb7c383c349fdef8b115fd6616282ffc246ad69ae654811033bbcd`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2012-to-03-11-2013.csv`: `624d86e62904c9302d97cfcafffe47a0a82a73c71304b357991b798b684102fe`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2013-to-03-11-2014.csv`: `7862ff9403290e4743feb92af5fa2fce8f80c6b389b251716bcf4ae6abc58d0b`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2014-to-03-11-2015.csv`: `2306cd4fb06a995c4a83e26b7400c5929573870ce09ce2a04bb73d9310a515e5`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2015-to-03-11-2016.csv`: `d02650eafb9946377cbbe808d77c8660737610520c617c1be12d73401d60c890`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2016-to-03-11-2017.csv`: `a7e9a5696edb5f2a70dc63f5d180fe8f32df561dee9d622d283bc0cc02d526e6`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2017-to-03-11-2018.csv`: `19c79dc8f85cf0f49b2c2932e9d4b261d7ceb48e035239a8b9bb910bc387404a`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2018-to-03-11-2019.csv`: `b95e91fa698a49a27abfc227245a2b535e3e93b8a1021e404fdbd21f9901d0ee`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2019-to-03-11-2020.csv`: `ce1053f3f392b2609b2ba38e3675a329815dcf676df2a9678e2768a3d7defd04`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2020-to-03-11-2021.csv`: `c8237ada80a0000534b5695a67e9a90072bef539af4b5b59d952e1f3e0b41d78`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2021-to-03-11-2022.csv`: `5d8bb2305c9df88353553bc0c662f3a2e00542e830451249bf488cbfd344a511`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2022-to-03-11-2023.csv`: `1061957b64faf1694f2056e3ac590bd1a42a072b54e8aec57603a4f0140afea5`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2023-to-03-11-2024.csv`: `ff33dc2072af20f0b48c4bec893cff611d7fbe98d681b51a82204456023c1a3d`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2024-to-03-11-2025.csv`: `05e44ded91171b577f807564760ae40479f79549d79f00fff14f456afdccb52e`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2025-to-11-09-2026.csv`: `d5d78a3d3881a16868b4cd61659c7c9e6537a54b17df26dcd9141b9a13e7f039`
- Processed: `data/processed/india/market/nse_india_vix_daily.csv` SHA-256 `e7a35131fbe948ab7105ee14d86580877083524cd1c17933add387dd2977b5e3`
### `nse_india_vix_daily`
- Earliest: `2010-07-19`
- Latest: `2026-09-11`
- Observations: 4004
- Unique dates: 4004
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/4004 (0.00%)
  - `open`: 0/4004 (0.00%)
  - `high`: 0/4004 (0.00%)
  - `low`: 0/4004 (0.00%)
  - `close`: 0/4004 (0.00%)
  - `prev_close`: 0/4004 (0.00%)
  - `change`: 0/4004 (0.00%)
  - `pct_change`: 0/4004 (0.00%)
- Calendar: 17 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `NSE`
- Raw artifacts: `30 annual files`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112004to01112005.csv`: `a5efd1ecac5d4a44c927093dbb8472c8991cf6153e1555d1d6aa11ebcab104a0`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112005to01112006.csv`: `af99869f988ee03a1fdc8084d1eff082a97a20f130b4ac465658f081a2a4bc07`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112006to01112007.csv`: `623ec36698fcf5fc057eac8348f3532d959a084dbbc1877fc99a26e687887cbf`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112007to31102008.csv`: `ce629419eebcf1a8edb8bff749b171afd63cd6c82af9c47b4e28b6d48d5bd99e`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112000to02112001.csv`: `84f17c90be61055a2563b724c28efc0add38a1de31e27aafaaf24157f6b419f0`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112001to02112002.csv`: `072f6953ca3d066ed35f8d1d74f33bcad159c8bf0d2eb34568189894dd17ff7d`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112002to02112003.csv`: `8c648ea77a8efc6aa4bd6a65fc4e2d08cc805e7a9e29b5de77c4dc774b63ab30`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112003to01112004.csv`: `0c007e00d0be8a35e66dde3530534689b691731efc61b2f657041b3d703b9caf`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111996to03111997.csv`: `dc5006508d1d95abd3579fc39bbb4bdbff18a3f859ef8e0d66259b616b49a258`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111997to03111998.csv`: `fe1a277751b9f5d389a17d6870eb354bf08f749985e813f3b29c3ad3401401c5`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111998to03111999.csv`: `7dd78070612ef1831f1738584de7b225e5b360e28ebb33e17410d92d770e5ae1`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111999to02112000.csv`: `c1297a653facf05cfaa3f0c7677d1eed2ba74f813698e6760f767370ba30ed91`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_28102024to28102025.csv`: `b0a7332f12f82530ab15fb3b6c71275f7caa2123b94ade1e1f1f9c9b0cda8791`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_28102025to11092026.csv`: `d9f7bbb9caeff3e84c5e4d5a5c6dd8cb4826add6704afa263f84bb99165c0da7`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102020to29102021.csv`: `8a789897d86d27d8034fae256c21da20748d0df56ad1966589a9a7a94a1307c7`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102021to29102022.csv`: `1b69544c8a3e41fa9e066f92b8a7f9b2804ad56b4fb7785387f9f96c231c1d8c`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102022to29102023.csv`: `dd04db22e49e84da2ac657c824cde5b7005f51191ca8980e4e1ed36fa2521f17`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102023to28102024.csv`: `7770ff52216fd1e833f8ad19d6528c7e4f82572947d7c6a1754df608ede0822f`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102012to30102013.csv`: `241eb11cd33e2ab9f3df2df2c196e5ce3fefd8bf6b3c353659939cac63f8a34b`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102013to30102014.csv`: `efb4f27b89bfc23afa0dd6e8389bef086a0e0d40cc5d7ab1ccf4a3fc8ad65668`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102014to30102015.csv`: `dd7d77b8723f1598300e9a536f5075b4121ae9f08fdb95410eb5976d6299c5c4`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102015to29102016.csv`: `71a53e6c07bfaea9bee4a4adbb9ad56aa7e4b7f103c691bbc88d818e934eac69`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102016to29102017.csv`: `1099a931fac3630f1009ddeed9453874759a5d8bf5772be54501170b236d1ec7`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102017to30102018.csv`: `6413e342f8d63c884aa9bfaa4caf15fc92f135593fb4dfb1a6c74d1e86e8f63f`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102018to30102019.csv`: `69ce58c6ccdcaf787520c0ee0ff542a2b3e6a49706748f7be40e3e55c9bd83c1`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102019to29102020.csv`: `ee3cbdf6efafc09c5781c3709a0d6d11a27b47641c2a2f5481a4a3ae21569314`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102008to31102009.csv`: `f4e7574c6952073752ebb2c77e4d2dd5288c67323e8438e580a1770b53c36757`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102009to31102010.csv`: `0bcb750cc6fa1a176b0a0da930a252b82ed9fdb63b18bde2fbd40ee212554767`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102010to31102011.csv`: `cc1f4487044cd623c56ce70bc950110714e83ad07923723aca79f5ff43ee9705`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102011to30102012.csv`: `d103a71535a23f3f37b087dc50637dd8c347ac2d60ba59359d4e291641f0765a`
- Processed: `data/processed/india/market/nse_nifty_500_daily.csv` SHA-256 `217149c2aebdc8c531ff465df15c07138760d783497441eceb8f43da991d35a1`
### `nse_nifty_500_daily`
- Earliest: `1996-11-04`
- Latest: `2026-09-11`
- Observations: 7413
- Unique dates: 7413
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/7413 (0.00%)
  - `open`: 0/7413 (0.00%)
  - `high`: 0/7413 (0.00%)
  - `low`: 0/7413 (0.00%)
  - `close`: 0/7413 (0.00%)
- Calendar: 40 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `NSE`
- Raw artifacts: `29 annual files`
  - `data/raw/india/indices/NIFTY 50-03-11-1997-to-03-11-1998.csv`: `366b0bab09ed341c21f4e5affc2e13cbb5c87bc915ef51af8272f99426f66d2f`
  - `data/raw/india/indices/NIFTY 50-03-11-1998-to-03-11-1999.csv`: `3632fed1f09095adce48d472322c7dbfb6a763a41f1ece8b2aec8db77c62b45a`
  - `data/raw/india/indices/NIFTY 50-03-11-1999-to-03-11-2000.csv`: `eb8d5af29b5a84fb764990d7aac4650db80c368301aea6d87c9eba8eb950cdca`
  - `data/raw/india/indices/NIFTY 50-03-11-2000-to-03-11-2001.csv`: `48bb8f7249deb5180dd3e3eeceaa3fc9d3191387d8a74a5ee69cfa51249c1f62`
  - `data/raw/india/indices/NIFTY 50-03-11-2001-to-03-11-2002.csv`: `f6f936cf62c3bd634ba274627d606fd791caa71e303dae19002ade02a97522a2`
  - `data/raw/india/indices/NIFTY 50-03-11-2002-to-03-11-2003.csv`: `4578bcc632aee42f54a0b4d0dc92442c5b8b0e11dde3291a5e7bdb22d14068b4`
  - `data/raw/india/indices/NIFTY 50-03-11-2003-to-03-11-2004.csv`: `d937a5d7d2bce8b91edfe261c511d7405ac89257eabe6e93112060f2b323443b`
  - `data/raw/india/indices/NIFTY 50-03-11-2004-to-03-11-2005.csv`: `eaba1f05f154513b2d06618e398a8e85bd1683966d2fcbd94d2fb8ae560b38ba`
  - `data/raw/india/indices/NIFTY 50-03-11-2005-to-03-11-2006.csv`: `0b49982170f7e5189fe860c1224dbe23bbd67832221de793ba5a143a715b41ef`
  - `data/raw/india/indices/NIFTY 50-03-11-2006-to-03-11-2007.csv`: `489e63ff6aea0976faf6a015c1a0addeccb775b0c5c786c126615254690c1ca2`
  - `data/raw/india/indices/NIFTY 50-03-11-2007-to-03-11-2008.csv`: `a56c480a788667e8b47008a596823113df183096b4e68105b58f47334d8fa04f`
  - `data/raw/india/indices/NIFTY 50-03-11-2008-to-03-11-2009.csv`: `2605e8eebf0bd123105a40f8a8b23b3202770928e4226e09a17c7c912941bcf3`
  - `data/raw/india/indices/NIFTY 50-03-11-2009-to-03-11-2010.csv`: `81424991f6d803adb95aa73cb669876b8a366e34d8d04274f09814600921d0ab`
  - `data/raw/india/indices/NIFTY 50-03-11-2010-to-03-11-2011.csv`: `0b4e62414e080843969f3aa1f1748ddfe20f5d0c13bd0427c3b4d346686296d4`
  - `data/raw/india/indices/NIFTY 50-03-11-2011-to-03-11-2012.csv`: `76dd025b4936f94b7d18a62c75fa82258c3f0f7e689e0a70a0a72bec1b23ad1d`
  - `data/raw/india/indices/NIFTY 50-03-11-2012-to-03-11-2013.csv`: `e2a2d361a76b85f87c642d3852c85791dd723a1ffea246a38d4ba63e7f254969`
  - `data/raw/india/indices/NIFTY 50-03-11-2013-to-03-11-2014.csv`: `b785239e9b250231d1df64529ea629370a755474491c969497c032d2d60fc495`
  - `data/raw/india/indices/NIFTY 50-03-11-2014-to-03-11-2015.csv`: `41bfc41638bef260830467cf3ba109d0d009849a9f9d33fdb9c7d81fe75f26c7`
  - `data/raw/india/indices/NIFTY 50-03-11-2015-to-03-11-2016.csv`: `e402cc0c0a7267fe795f5d89251904e5112382c7236b37663ff7781b42205f58`
  - `data/raw/india/indices/NIFTY 50-03-11-2016-to-03-11-2017.csv`: `eae2df9bdc73d44f490621ce34fe0b6366df3c91b354a47be51b2ab4648a5428`
  - `data/raw/india/indices/NIFTY 50-03-11-2017-to-03-11-2018.csv`: `494420fa872e1c3c9d38ecf9feb7eb7c3755b5b436ee8545d67f68dce8c18dd5`
  - `data/raw/india/indices/NIFTY 50-03-11-2018-to-03-11-2019.csv`: `81bf230522f292363200922551870cbc3843a40c76c0da84be10383860c21e8c`
  - `data/raw/india/indices/NIFTY 50-03-11-2019-to-03-11-2020.csv`: `064c507b2dd5768ff8e7c7254bb3e1f93b9b3e2a24bf615674753d5553788ae4`
  - `data/raw/india/indices/NIFTY 50-03-11-2020-to-03-11-2021.csv`: `076412647aeef2964cb218fe81be5ad27ec8af492b9cf6e5f90fd3dc8fc1353e`
  - `data/raw/india/indices/NIFTY 50-03-11-2021-to-03-11-2022.csv`: `f32200975b25f1e62f6da4f4db743d1bf1105e6e305d4a72cd27213540585c58`
  - `data/raw/india/indices/NIFTY 50-03-11-2022-to-03-11-2023.csv`: `12344a323fd3e5c7d48fb7b42e1e845324337c81b9ec281d5be7c93efc9297c6`
  - `data/raw/india/indices/NIFTY 50-03-11-2023-to-03-11-2024.csv`: `2e11609e8a0cf28b7563772cab5ad6cadfb5cfe4e91d37c816de22a69c240e63`
  - `data/raw/india/indices/NIFTY 50-03-11-2024-to-03-11-2025.csv`: `2978462d63df5d84b4f54bfa3aa0da6943c2c9fb44dd02afd54feeca3afa777e`
  - `data/raw/india/indices/NIFTY 50-03-11-2025-to-11-09-2026.csv`: `352711475a947e060a153cc4a689fb3f34be2f441a05c9773159de5ea62431ea`
- Processed: `data/processed/india/market/nse_nifty_50_daily.csv` SHA-256 `beff7b005ecf5a2134bc09ad0079af48c29a5071ea63c6657aaff9a2e349c09e`
### `nse_nifty_50_daily`
- Earliest: `1997-11-03`
- Latest: `2026-09-11`
- Observations: 7183
- Unique dates: 7183
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/7183 (0.00%)
  - `open`: 0/7183 (0.00%)
  - `high`: 0/7183 (0.00%)
  - `low`: 0/7183 (0.00%)
  - `close`: 0/7183 (0.00%)
  - `volume`: 0/7183 (0.00%)
  - `turnover`: 0/7183 (0.00%)
- Calendar: 37 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `NSE`
- Raw SHA-256: `933cf5dc6dd4efe3b8db8ce6ecd6ecb2582929f5e0b4faffdb88e11cf4efdfbe`
- Processed: `data/processed/india/market/nse_trading_calendar_2026.csv` SHA-256 `3090d9f89784f264f7ee5b210c8f85a9f4851fb2bd71daa3754aedf536e08427`
### `nse_trading_holidays_2026`
- Earliest: `2026-01-01`
- Latest: `2026-12-25`
- Observations: 239
- Unique dates: 25
- Duplicate timestamps: not applicable (category membership)
- Duplicate identifier pairs: 0
- Temporal gaps above threshold: 17
- Note: Repeated dates are evaluated with identifier columns; date repetition alone is not treated as a duplicate record.
- Note: INFO: 17 gap(s) detected. First: (datetime.date(2026, 1, 1), datetime.date(2026, 1, 15))
- Note: Repeated dates are legitimate market-segment membership; duplicate records are evaluated by `(market_segment, trading_date)`.

- Source: `RBI`
- Raw artifacts: `1 annual files`
  - `data/raw/india/fixed_income/50 Macroeconomic Indicators.xlsx`: `1072bfe9347c6c510c495d2d0894dc6e3931b23775a68faab5c74391f52e679d`
- Processed: `data/processed/india/market/rbi_gsec_10y_weekly.csv` SHA-256 `fb5c4845f143b11749df283d07d92b27ab050e207f714e329af38a54e18581a4`
### `rbi_gsec_10y_yield`
- Earliest: `2017-10-13`
- Latest: `2026-09-04`
- Observations: 465
- Unique dates: 465
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `observation_date`: 0/465 (0.00%)
  - `tenor`: 0/465 (0.00%)
  - `yield_pct`: 0/465 (0.00%)
- Calendar: 0 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `RBI`
- Raw artifacts: `1 annual files`
  - `data/raw/india/fixed_income/50 Macroeconomic Indicators.xlsx`: `1072bfe9347c6c510c495d2d0894dc6e3931b23775a68faab5c74391f52e679d`
- Processed: `data/processed/india/market/rbi_tbill_91d_weekly.csv` SHA-256 `6ab7fff49cfb47a530839db2c485ea4b895eb62a00df169deea258e2d818d445`
### `rbi_gsec_91d_yield`
- Earliest: `2017-10-13`
- Latest: `2026-09-04`
- Observations: 458
- Unique dates: 458
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `observation_date`: 0/458 (0.00%)
  - `tenor`: 0/458 (0.00%)
  - `yield_pct`: 0/458 (0.00%)
- Temporal gaps above threshold: 5
- Calendar: 0 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)
- Note: INFO: 5 gap(s) detected. First: (datetime.date(2023, 3, 24), datetime.date(2023, 4, 7))

- Source: `RBI`
- Raw artifacts: `1 annual files`
  - `data/raw/india/currency/BankWise.xls`: `4b2b6cd815a53357ebdb3d72cc4728a80922fa5f57bafc26495d6dc3600a5068`
- Processed: `data/processed/india/market/rbi_usd_inr_daily.csv` SHA-256 `878d4e0ecd080e8d4700a7d1e947301db904f9b38f4b8f21149d51da668aff6b`
### `rbi_usd_inr_daily`
- Earliest: `1998-08-25`
- Latest: `2026-09-11`
- Observations: 5878
- Unique dates: 5878
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/5878 (0.00%)
  - `rate`: 0/5878 (0.00%)
- Temporal gaps above threshold: 2
- Calendar: 2 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)
- Note: INFO: 2 gap(s) detected. First: (datetime.date(2018, 7, 9), datetime.date(2018, 7, 24))

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
  - `nse_india_vix_daily`: Dataset is not experiment-eligible.
  - `nse_nifty_500_daily`: Dataset is not experiment-eligible.
  - `nse_nifty_50_daily`: Dataset is not experiment-eligible.
  - `rbi_gsec_10y_yield`: Dataset is not experiment-eligible.
  - `rbi_gsec_364d_yield`: Dataset not audited — no coverage data available.
  - `rbi_gsec_91d_yield`: Dataset is not experiment-eligible.
  - `rbi_policy_rate_events`: Dataset not audited — no coverage data available.
  - `rbi_usd_inr_daily`: Dataset is not experiment-eligible.

## 8. Data-quality blockers

- No artifact read errors were encountered.

## 9. Leakage findings

- Leakage validation status: **EVALUATED**
- Datasets checked: corporate_actions, preprocessing, price
- Confirmed leaks: 0
- Potential leaks: 1
- Mitigated issues: 0
- Unresolved issues: 0
- Gold futures must remain contract-level until a roll method is selected and independently audited.

## 10. Recommended next methodological decision

Complete official-source acquisition and release-date verification for the mandatory datasets. Then review this audit to define the longest clean common period before selecting any temporal split boundaries.
