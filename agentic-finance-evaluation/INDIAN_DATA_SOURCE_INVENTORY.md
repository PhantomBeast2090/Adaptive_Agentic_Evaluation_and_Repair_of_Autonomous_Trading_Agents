# Indian Multi-Asset Data Source Inventory

Status is intentionally separated into **verified source**, **expected
coverage**, and **actually acquired coverage**. A source is not considered
acquired until a non-empty raw artifact has been validated and its manifest
contains a deterministic SHA-256 hash.

| Dataset | Tier / asset class | Primary source and official source | Expected fields and native frequency | Availability / revision / calendar considerations | Acquisition mechanism | Raw / processed location | Current status |
|---|---|---|---|---|---|---|---|
| NIFTY 50 | A / equity index | NSE, [historical index data](https://www.nseindia.com/market-data/historical-index-data) | date, OHLC, volume, turnover; daily | NSE trading calendar; index history coverage must be measured | Manual NSE CSV; adapter normalizes headers | `data/raw/india/indices/`, `data/processed/india/market/` | Verified source; expected long history; not acquired in this checkout |
| NIFTY 500 | A / equity index | NSE historical index data | date, OHLC, volume, turnover; daily | NSE calendar; inception differs from NIFTY 50 | Manual NSE CSV | Same as above | Verified source; coverage pending |
| NIFTY Bank | B / sector index | NSE historical index data | date, OHLC and available analytics; daily | NSE calendar; sector membership changes | Manual NSE CSV | Same as above | Verified source; coverage pending |
| NIFTY IT | B / sector index | NSE historical index data | date, OHLC and available analytics; daily | NSE calendar; sector membership changes | Manual NSE CSV | Same as above | Verified source; coverage pending |
| NIFTY Pharma | B / sector index | NSE historical index data | date, OHLC and available analytics; daily | NSE calendar; sector membership changes | Manual NSE CSV | Same as above | Verified source; coverage pending |
| NIFTY FMCG | B / sector index | NSE historical index data | date, OHLC and available analytics; daily | NSE calendar; sector membership changes | Manual NSE CSV | Same as above | Verified source; coverage pending |
| NIFTY Auto | B / sector index | NSE historical index data | date, OHLC and available analytics; daily | NSE calendar; sector membership changes | Manual NSE CSV | Same as above | Verified source; coverage pending |
| NIFTY Next 50 | B / broad index | NSE historical index data | date, OHLC and available analytics; daily | NSE calendar; constituent changes are not retroactively assumed | Manual NSE CSV | Same as above | Verified source; coverage pending |
| Selected NSE equities | A / equity security | NSE bhavcopy/security files | symbol, ISIN, series, OHLC, VWAP, quantity, turnover, trades, delivery; daily | Security identifiers and series are mandatory where supplied; corporate actions are not silently adjusted | Manual bhavcopy/security CSV | `data/raw/india/equities/`, `data/processed/india/instruments/` | Verified source; universe not selected and data not acquired |
| India VIX | B / volatility index | NSE, [India VIX](https://www.nseindia.com/market-data/india-vix) | date, OHLC, previous close, change, percent change; daily | NSE calendar; distinct from CBOE VIX | Session API attempted; manual CSV fallback | `data/raw/india/india_vix/`, `data/processed/india/market/` | Verified source; not acquired |
| Market breadth | B / breadth | NSE market statistics | date, advances, declines, unchanged; daily/event | NSE calendar; breadth definitions must be retained | Manual NSE report or official endpoint | `data/raw/india/breadth/`, `data/processed/india/market/` | Verified source family; not acquired |
| 10Y G-Sec benchmark | A / fixed income state | RBI/DBIE, [DBIE](https://data.rbi.org.in/) | observation date, tenor, yield, price where available; daily | RBI/market-day calendar; publication date retained where supplied | RBI/DBIE export or manual file | `data/raw/india/fixed_income/`, `data/processed/india/market/` | Verified source family; not acquired |
| 5Y G-Sec benchmark | A / fixed income state | RBI/DBIE | observation date, tenor, yield, price; daily | Same as 10Y benchmark | RBI/DBIE export or manual file | Same as above | Extension; not acquired |
| 91-day Treasury Bill | A / fixed income state | RBI/DBIE | observation date, tenor, yield/rate; daily or auction frequency | Auction/event frequency must not be daily-forward-filled without a rule | RBI/DBIE export or manual file | Same as above | Verified source family; not acquired |
| 364-day Treasury Bill | A / fixed income state | RBI/DBIE | observation date, tenor, yield/rate; auction frequency | Auction dates and publication timing retained | RBI/DBIE export or manual file | Same as above | Verified source family; not acquired |
| USD/INR reference rate | A / currency | RBI/FBIL-compatible reference series | date, INR per USD, source, frequency; daily | Financial-day calendar; reference-rate timestamp retained | RBI/DBIE export or manual file | `data/raw/india/currency/`, `data/processed/india/market/` | Verified source family; not acquired |
| RBI repo rate | A / policy state | RBI monetary policy releases | observation date, availability date, rate, change, stance; event-based | Announcement/availability date is first information date; revisions/events retained | RBI release table/manual file | `data/raw/india/fixed_income/`, `data/processed/india/macro/` | Verified source; not acquired |
| CPI combined | C / macro | MoSPI, [CPI](https://mospi.gov.in/) | observation month, availability/release date, value, unit, revision; monthly | Release date is not observation month; vintage/revision must be retained | Release-date CSV plus value CSV; estimated lag is explicitly flagged | `data/raw/india/macro/`, `data/processed/india/macro/` | Verified source; not acquired |
| IIP | C / macro | MoSPI | observation month, availability/release date, index/value, revision; monthly | Release date and vintage are first-class fields | Release-date CSV plus value CSV | Same as above | Verified source; not acquired |
| MCX Gold futures | A / gold | MCX, [historical data](https://www.mcxindia.com/market-data/historical-data) | contract, expiry, trade date, OHLC, settlement, OI, volume, turnover; daily | Individual contracts preserved; no concatenation; roll cannot use future knowledge | Individual contract CSVs; manual download fallback | `data/raw/india/gold/`, `data/processed/india/instruments/` | Verified source; not acquired |
| Brent crude | C / exogenous crude | EIA, [petroleum data](https://www.eia.gov/petroleum/) | date, benchmark, USD price; daily | Non-Indian source explicitly marked; global business-day calendar | Official EIA download/API or manual file | `data/raw/india/crude/`, `data/processed/india/macro/` | Secondary contextual source; not acquired |

## Adapter limitations

NSE and MCX commonly require session cookies, browser downloads, or
registration. RBI/DBIE and MoSPI exports can change format and may not expose
stable query URLs. The adapters therefore accept researcher-supplied files and
record `pending_manual_download` rather than creating empty files, substituting
retail APIs, or claiming coverage that has not been observed.

## Manifest evidence rule

Each acquired artifact must have a manifest under
`data/manifests/india/`. The manifest records the exact source URL or manual
source description, retrieval timestamp, raw SHA-256, processing parameters,
coverage, missingness, and validation status. Raw files are immutable evidence;
processed files must be separate artifacts with their own hash.

## Cross-dataset methodological rules

- **Publication timing:** market datasets use their exchange/financial-day
  timestamp; CPI, IIP, and RBI policy records use an explicit release or
  availability date rather than assuming observation date equals release date.
- **Revisions:** macro and policy vintages retain revision/version metadata and
  are not overwritten in the agent information set.
- **Corporate actions:** NSE security prices remain unadjusted unless a source
  and adjustment event set are explicitly documented.
- **Contract rolls:** MCX gold files remain individual contracts. A continuous
  series and roll rule are a later, separately audited methodological decision.
- **Calendar:** weekdays are only a preliminary heuristic. Official exchange
  holiday calendars must be used before constructing a final aligned dataset.
