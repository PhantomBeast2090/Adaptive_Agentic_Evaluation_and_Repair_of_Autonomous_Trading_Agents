"""V2 decision-time feature builder for the M2 representation experiment.

Additive layer BESIDE V1 (``evaluation/attribution/features.py``). V1
semantics are untouched; this module never imports outcome fields into X
and raises on any retrospective key, mirroring the V1 guard.

PIT doctrine (every feature, no exceptions):
  * instrument/market/cross-market bars: closes strictly BEFORE the
    decision timestamp (``date < T`` on ISO strings; never ``<=``).
  * macro: vintage-gated — latest row with ``availability_date <= T``
    (RBI policy announcements gated on ``announcement_date <= T``, the
    documented ``allow_pre_observation`` exception).
  * portfolio: decision-time ``portfolio_before`` snapshot from the
    frozen ``baseline_result.json`` trajectory only.
  * context: actual ``agent_context_version`` recorded at decision time.
  * outcomes (forward returns, MAE/MFE, hold/opportunity): NEVER in X;
    lives in the ``outcomes`` block as RETROSPECTIVE_EVALUATION_ONLY.

Frozen V2 allowlist: 23 features. Extending it after inspecting results
is forbidden by the pre-registered protocol; any future representation
is a V3 builder, not an edit here.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
from typing import Any, Dict, List, Mapping, Optional, Tuple

from evaluation.attribution.features import ADVERSE_BAND, RETROSPECTIVE_OUTCOMES

# ---------------------------------------------------------------------------
# Frozen allowlist + provenance (pre-registered; do not extend post-hoc)
# ---------------------------------------------------------------------------

DECISION_TIME_FEATURES_V2 = (
    # instrument-level (per-decision equity, strict <T bars)
    "instrument_return_1d",
    "instrument_return_3d",
    "instrument_return_5d",
    "instrument_return_10d",
    "instrument_volatility_10d",
    "instrument_dist_high_20d",
    "instrument_dist_low_20d",
    "instrument_volume_change_5d",
    # market-level (Nifty 50, strict <T bars)
    "nifty_return_1d",
    "nifty_return_3d",
    "nifty_return_5d",
    "nifty_volatility_10d",
    # cross-market (strict <T bars)
    "usdinr_return_5d",
    "vix_change_5d",
    "gold_return_5d",
    # macro (vintage/announcement-gated only)
    "rbi_policy_rate_pct",
    "rbi_stance",
    "latest_cpi",
    "latest_iip",
    # portfolio (decision-time snapshot only)
    "drawdown",
    "holdings_value",
    "cumulative_costs",
    # context (actual version at T; expected constant C0)
    "active_context_version",
)

NUMERIC_FEATURES_V2 = tuple(n for n in DECISION_TIME_FEATURES_V2 if n not in (
    "rbi_stance", "active_context_version"))

CATEGORICAL_FEATURES_V2 = ("rbi_stance", "active_context_version")

# Pre-first-fill semantics mirror V1: absent position-derived state means
# flat, not unknown. Drawdown is always computable (first decision defines
# the episode peak), so it is not zero-filled.
ZERO_FILL_FEATURES_V2: Tuple[str, ...] = ()

# Pre-registered interpretation rule (applied in reporting, never as a
# builder mutation): a macro feature with >80% missingness is dropped
# with evidence, never imputed into significance.
MACRO_DROP_MISSINGNESS_THRESHOLD = 0.80
MACRO_FEATURES_V2 = (
    "rbi_policy_rate_pct", "rbi_stance", "latest_cpi", "latest_iip")

# Per-feature provenance. ``agent_observes`` records whether the trading
# agent itself consumed the signal at decision time (all False except the
# three V1-overlapping portfolio/context pass-throughs the agent's
# readers touch: cash-adjacent state is NOT in V2; only context version
# overlaps and it is constant). Unused != useful until tested.
FEATURE_PROVENANCE_V2: Dict[str, Dict[str, str]] = {
    "instrument_return_1d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "closes strictly < T; return over last 2 eligible closes",
        "derivation": "(c[-1]-c[-2])/c[-2] on per-symbol close series",
        "agent_observes": "no", "missingness": "none expected (2019+ daily coverage)"},
    "instrument_return_3d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "closes strictly < T",
        "derivation": "(c[-1]-c[-4])/c[-4]; None if <4 eligible closes",
        "agent_observes": "no", "missingness": "window-edge only"},
    "instrument_return_5d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "closes strictly < T",
        "derivation": "(c[-1]-c[-6])/c[-6]; None if <6 eligible closes",
        "agent_observes": "no", "missingness": "window-edge only"},
    "instrument_return_10d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "closes strictly < T",
        "derivation": "(c[-1]-c[-11])/c[-11]; None if <11 eligible closes",
        "agent_observes": "no", "missingness": "early-window rows"},
    "instrument_volatility_10d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "1d returns from closes strictly < T",
        "derivation": "sample stdev of last 10 eligible 1d returns",
        "agent_observes": "no", "missingness": "early-window rows"},
    "instrument_dist_high_20d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "highs strictly < T",
        "derivation": "(c[-1]-max(high[-20:]))/max(high[-20:])",
        "agent_observes": "no", "missingness": "early-window rows"},
    "instrument_dist_low_20d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv",
        "pit_rule": "lows strictly < T",
        "derivation": "(c[-1]-min(low[-20:]))/min(low[-20:])",
        "agent_observes": "no", "missingness": "early-window rows"},
    "instrument_volume_change_5d": {
        "source": "data/processed/india/equities/nse_equity_daily.csv:traded_quantity",
        "pit_rule": "volumes strictly < T",
        "derivation": "v[-1]/mean(v[-6:-1])-1; None on zero/empty window",
        "agent_observes": "no", "missingness": "early-window rows"},
    "nifty_return_1d": {
        "source": "data/processed/india/market/nse_nifty_50_daily.csv",
        "pit_rule": "index closes strictly < T",
        "derivation": "(c[-1]-c[-2])/c[-2]",
        "agent_observes": "no", "missingness": "none expected"},
    "nifty_return_3d": {
        "source": "data/processed/india/market/nse_nifty_50_daily.csv",
        "pit_rule": "index closes strictly < T",
        "derivation": "(c[-1]-c[-4])/c[-4]",
        "agent_observes": "no", "missingness": "none expected"},
    "nifty_return_5d": {
        "source": "data/processed/india/market/nse_nifty_50_daily.csv",
        "pit_rule": "index closes strictly < T",
        "derivation": "(c[-1]-c[-6])/c[-6]",
        "agent_observes": "no", "missingness": "none expected"},
    "nifty_volatility_10d": {
        "source": "data/processed/india/market/nse_nifty_50_daily.csv",
        "pit_rule": "1d returns from closes strictly < T",
        "derivation": "sample stdev of last 10 eligible 1d returns",
        "agent_observes": "no", "missingness": "none expected"},
    "usdinr_return_5d": {
        "source": "data/processed/india/market/rbi_usd_inr_daily.csv",
        "pit_rule": "reference rates strictly < T (sparse grid: weekends absent)",
        "derivation": "(r[-1]-r[-6])/r[-6] on eligible rates",
        "agent_observes": "no", "missingness": "sparse-grid edges only"},
    "vix_change_5d": {
        "source": "data/processed/india/market/nse_india_vix_daily.csv",
        "pit_rule": "VIX closes strictly < T",
        "derivation": "(v[-1]-v[-6])/v[-6]",
        "agent_observes": "no (V1 used vix level t-1; this is the change)",
        "missingness": "none expected (2010+ daily coverage)"},
    "gold_return_5d": {
        "source": "data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv",
        "pit_rule": "GOLDAUG2023 contract closes strictly < T; no cross-contract mixing",
        "derivation": "(c[-1]-c[-6])/c[-6]; None when contract unlisted",
        "agent_observes": "no",
        "missingness": "honest high missingness expected (contract calendar gaps)"},
    "rbi_policy_rate_pct": {
        "source": "data/processed/india/macro/rbi_policy_rate_events.csv",
        "pit_rule": "announcement_date <= T (announcement-gated exception)",
        "derivation": "rate_pct of latest eligible event",
        "agent_observes": "no", "missingness": "pre-2008 decisions only"},
    "rbi_stance": {
        "source": "data/processed/india/macro/rbi_policy_rate_events.csv",
        "pit_rule": "announcement_date <= T; empty stance kept as missing",
        "derivation": "stance string of latest eligible event",
        "agent_observes": "no", "missingness": "early-sample empty stances"},
    "latest_cpi": {
        "source": "data/processed/india/macro/mospi_cpi_combined_monthly.csv",
        "pit_rule": "availability_date <= T (vintage-gated; stale but valid)",
        "derivation": "cpi_index of latest eligible vintage + staleness days in manifest",
        "agent_observes": "no", "missingness": "pre-2015 decisions only"},
    "latest_iip": {
        "source": "data/processed/india/macro/mospi_iip_general_monthly.csv",
        "pit_rule": "availability_date <= T (vintage-gated; stale but valid)",
        "derivation": "iip_index of latest eligible vintage + staleness days in manifest",
        "agent_observes": "no", "missingness": "pre-availability decisions only"},
    "drawdown": {
        "source": "frozen baseline_result.json portfolio_before.total_equity (per-episode order)",
        "pit_rule": "decision-time snapshot + strictly prior same-episode snapshots",
        "derivation": "(eq-peak)/peak over episode peak to current index",
        "agent_observes": "no", "missingness": "none (first decision defines peak)"},
    "holdings_value": {
        "source": "frozen baseline_result.json portfolio_before.holdings_value",
        "pit_rule": "decision-time snapshot",
        "derivation": "pass-through float",
        "agent_observes": "no", "missingness": "none expected"},
    "cumulative_costs": {
        "source": "frozen baseline_result.json portfolio_before.cumulative_costs",
        "pit_rule": "decision-time snapshot",
        "derivation": "pass-through float",
        "agent_observes": "no", "missingness": "none expected"},
    "active_context_version": {
        "source": "frozen decision_table.csv agent_context_version",
        "pit_rule": "actual version recorded at T",
        "derivation": "pass-through string; expected constant C0-empty-store (zero variance)",
        "agent_observes": "n/a (delivery mechanism, not signal)",
        "missingness": "none expected; zero variance documented, not manufactured"},
}

V2_SOURCE_FILES = (
    "data/processed/india/equities/nse_equity_daily.csv",
    "data/processed/india/market/nse_nifty_50_daily.csv",
    "data/processed/india/market/nse_india_vix_daily.csv",
    "data/processed/india/market/rbi_usd_inr_daily.csv",
    "data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv",
    "data/processed/india/macro/rbi_policy_rate_events.csv",
    "data/processed/india/macro/mospi_cpi_combined_monthly.csv",
    "data/processed/india/macro/mospi_iip_general_monthly.csv",
)

GOLD_CONTRACT = "GOLDAUG2023"


# ---------------------------------------------------------------------------
# Internal helpers (pure, deterministic)
# ---------------------------------------------------------------------------

def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _closes_before(pairs: List[Tuple[str, float]], stamp: str, k: int
                   ) -> List[float]:
    """Last k values with date strictly before stamp (ISO strings)."""
    out = [v for d, v in pairs if d < stamp]
    return out[-k:]


def _return(closes: List[float], lag: int) -> Optional[float]:
    if len(closes) <= lag or closes[-lag - 1] == 0:
        return None
    return (closes[-1] - closes[-lag - 1]) / closes[-lag - 1]


def _stdev_1d(closes: List[float], window: int = 10) -> Optional[float]:
    if len(closes) <= window:
        return None
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(len(closes) - window, len(closes))
            if closes[i - 1] != 0]
    if len(rets) < 2:
        return None
    try:
        return statistics.stdev(rets)
    except statistics.StatisticsError:
        return None


_CACHE: Dict[str, Any] = {}


def _load_equity(base_dir: str) -> Dict[str, Dict[str, List[Tuple[str, float]]]]:
    """Per-symbol (date, value) series for universe symbols only.

    Uses pandas for the ~4.2M-row file (csv scan exceeds 2 minutes);
    falls back to the csv module if pandas is unavailable.
    """
    key = f"equity:{base_dir}"
    if key in _CACHE:
        return _CACHE[key]
    path = os.path.join(
        base_dir, "data/processed/india/equities/nse_equity_daily.csv")
    symbols = ("RELIANCE", "TCS", "INFY")
    series: Dict[str, Dict[str, List[Tuple[str, float]]]] = {
        s: {"close": [], "high": [], "low": [], "volume": []} for s in symbols}
    try:
        import pandas as pd  # type: ignore
        frame = pd.read_csv(
            path, usecols=["observation_date", "symbol", "close",
                           "high", "low", "traded_quantity"])
        frame = frame[frame["symbol"].isin(symbols)].sort_values(
            "observation_date")
        for row in frame.itertuples(index=False):
            sym = str(row.symbol)
            if sym not in series:
                continue
            d = str(row.observation_date)
            c, h, lo = _num(row.close), _num(row.high), _num(row.low)
            if c is not None:
                series[sym]["close"].append((d, c))
            if h is not None:
                series[sym]["high"].append((d, h))
            if lo is not None:
                series[sym]["low"].append((d, lo))
            v = _num(row.traded_quantity)
            if v is not None:
                series[sym]["volume"].append((d, v))
    except ImportError:
        with open(path, newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("symbol") not in series:
                    continue
                sym = str(row["symbol"])
                d = str(row.get("observation_date") or "")
                c, h, lo = (_num(row.get("close")), _num(row.get("high")),
                            _num(row.get("low")))
                if c is not None:
                    series[sym]["close"].append((d, c))
                if h is not None:
                    series[sym]["high"].append((d, h))
                if lo is not None:
                    series[sym]["low"].append((d, lo))
                v = _num(row.get("traded_quantity"))
                if v is not None:
                    series[sym]["volume"].append((d, v))
        for sym in series:
            for leg in series[sym]:
                series[sym][leg].sort(key=lambda p: p[0])
    _CACHE[key] = series
    return series


def _load_pairs(base_dir: str, rel: str, date_col: str, val_col: str,
                extra_filter: Optional[Dict[str, str]] = None
                ) -> List[Tuple[str, float]]:
    key = f"{rel}:{base_dir}:{date_col}:{val_col}:{extra_filter}"
    if key in _CACHE:
        return _CACHE[key]
    out: List[Tuple[str, float]] = []
    with open(os.path.join(base_dir, rel), newline="") as handle:
        for row in csv.DictReader(handle):
            if extra_filter and any(
                    row.get(k) != v for k, v in extra_filter.items()):
                continue
            v = _num(row.get(val_col))
            d = str(row.get(date_col) or "")
            if v is not None and d:
                out.append((d, v))
    out.sort(key=lambda p: p[0])
    _CACHE[key] = out
    return out


def _load_rbi(base_dir: str) -> List[Dict[str, str]]:
    key = f"rbi:{base_dir}"
    if key in _CACHE:
        return _CACHE[key]
    with open(os.path.join(
            base_dir, "data/processed/india/macro/rbi_policy_rate_events.csv"),
            newline="") as handle:
        rows = sorted((r for r in csv.DictReader(handle)
                       if r.get("announcement_date")),
                      key=lambda r: str(r["announcement_date"]))
    _CACHE[key] = rows
    return rows


def _load_vintage(base_dir: str, rel: str, idx_col: str
                  ) -> List[Tuple[str, float]]:
    """(availability_date, index) sorted — vintage-gated lookup."""
    key = f"vintage:{rel}:{base_dir}"
    if key in _CACHE:
        return _CACHE[key]
    out: List[Tuple[str, float]] = []
    with open(os.path.join(base_dir, rel), newline="") as handle:
        for row in csv.DictReader(handle):
            a = str(row.get("availability_date") or "")
            v = _num(row.get(idx_col))
            if a and v is not None:
                out.append((a, v))
    out.sort(key=lambda p: p[0])
    _CACHE[key] = out
    return out


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_ml_dataset_v2(
    artefact_dirs: List[str],
    base_dir: str = ".",
) -> Dict[str, Any]:
    """Build the validated V2 multi-window ML dataset (read-only).

    Same trajectory join as V1 (decision_table.csv EXECUTED rows +
    baseline_result.json portfolio snapshots, file order = trajectory
    order); V2's additional legs come from processed CSVs under strict
    PIT rules documented in FEATURE_PROVENANCE_V2.
    """
    equity = _load_equity(base_dir)
    nifty = _load_pairs(
        base_dir, "data/processed/india/market/nse_nifty_50_daily.csv",
        "date", "close")
    vix = _load_pairs(
        base_dir, "data/processed/india/market/nse_india_vix_daily.csv",
        "date", "close")
    usdinr = _load_pairs(
        base_dir, "data/processed/india/market/rbi_usd_inr_daily.csv",
        "date", "rate")
    gold = _load_pairs(
        base_dir,
        "data/processed/india/instruments/"
        "mcx_gold_futures_individual_contracts.csv",
        "trade_date", "close",
        extra_filter={"contract_symbol": GOLD_CONTRACT})
    rbi = _load_rbi(base_dir)
    cpi = _load_vintage(
        base_dir, "data/processed/india/macro/mospi_cpi_combined_monthly.csv",
        "cpi_index")
    iip = _load_vintage(
        base_dir, "data/processed/india/macro/mospi_iip_general_monthly.csv",
        "iip_index")

    rows: List[Dict[str, Any]] = []
    for artefact in artefact_dirs:
        path = (artefact if os.path.isabs(artefact)
                else os.path.join(base_dir, artefact))
        with open(os.path.join(path, "decision_table.csv"), newline="") as handle:
            table = list(csv.DictReader(handle))
        with open(os.path.join(path, "baseline_result.json")) as handle:
            records = {r["decision_timestamp"] + "|" + str(i): r
                       for i, r in enumerate(
                           json.load(handle)["decision_records"])}
        order_in_session: Dict[str, int] = {}
        episode_peak: Dict[str, float] = {}
        for row in table:
            if row["participation_status"] != "EXECUTED":
                continue
            ts = row["decision_timestamp"]
            key_prefix = ts + "|"
            matches = sorted(k for k in records if k.startswith(key_prefix))
            rec = records[matches[order_in_session.get(ts, 0)
                                  % max(len(matches), 1)]] if matches else None
            order_in_session[ts] = order_in_session.get(ts, 0) + 1
            before = (rec.get("portfolio_before", {}) if rec else {}) or {}
            ep = row.get("episode_id") or ""
            eq = _num(row.get("total_equity_before"))
            peak = episode_peak.get(ep)
            if eq is not None:
                peak = eq if peak is None else max(peak, eq)
                episode_peak[ep] = peak
            drawdown = ((eq - peak) / peak if eq is not None and peak
                        else None)

            symbol = str(row.get("instrument") or "").split(":")[0]
            leg = equity.get(symbol, {"close": [], "high": [],
                                      "low": [], "volume": []})
            closes = _closes_before(leg["close"], ts, 21)
            highs = _closes_before(leg["high"], ts, 20)
            lows = _closes_before(leg["low"], ts, 20)
            vols = _closes_before(leg["volume"], ts, 6)
            ncloses = _closes_before(nifty, ts, 11)
            # NOTE: nifty_volatility_10d needs 11 closes; the return legs
            # need fewer — computed on a shared window is PIT-equivalent.
            u5 = _closes_before(usdinr, ts, 6)
            v5 = _closes_before(vix, ts, 6)
            g5 = _closes_before(gold, ts, 6)

            eligible_rbi = [e for e in rbi
                            if str(e["announcement_date"]) <= ts]
            last_rbi = eligible_rbi[-1] if eligible_rbi else None
            eligible_cpi = [p for p in cpi if p[0] <= ts]
            eligible_iip = [p for p in iip if p[0] <= ts]

            features: Dict[str, Any] = {
                "instrument_return_1d": _return(_closes_before(
                    leg["close"], ts, 2), 1),
                "instrument_return_3d": _return(_closes_before(
                    leg["close"], ts, 4), 3),
                "instrument_return_5d": _return(_closes_before(
                    leg["close"], ts, 6), 5),
                "instrument_return_10d": _return(_closes_before(
                    leg["close"], ts, 11), 10),
                "instrument_volatility_10d": _stdev_1d(
                    _closes_before(leg["close"], ts, 11)),
                "instrument_dist_high_20d": (
                    (closes[-1] - max(highs)) / max(highs)
                    if closes and highs and max(highs) != 0 else None),
                "instrument_dist_low_20d": (
                    (closes[-1] - min(lows)) / min(lows)
                    if closes and lows and min(lows) != 0 else None),
                "instrument_volume_change_5d": (
                    vols[-1] / (sum(vols[:-1]) / len(vols[:-1])) - 1
                    if len(vols) == 6 and sum(vols[:-1]) != 0 else None),
                "nifty_return_1d": _return(_closes_before(nifty, ts, 2), 1),
                "nifty_return_3d": _return(_closes_before(nifty, ts, 4), 3),
                "nifty_return_5d": _return(_closes_before(nifty, ts, 6), 5),
                "nifty_volatility_10d": _stdev_1d(ncloses),
                "usdinr_return_5d": _return(u5, 5),
                "vix_change_5d": _return(v5, 5),
                "gold_return_5d": _return(g5, 5),
                "rbi_policy_rate_pct": (
                    _num(last_rbi.get("rate_pct")) if last_rbi else None),
                "rbi_stance": (
                    (str(last_rbi.get("stance")).strip() or None)
                    if last_rbi else None),
                "latest_cpi": eligible_cpi[-1][1] if eligible_cpi else None,
                "latest_iip": eligible_iip[-1][1] if eligible_iip else None,
                "drawdown": drawdown,
                "holdings_value": _num(before.get("holdings_value")),
                "cumulative_costs": _num(before.get("cumulative_costs")),
                "active_context_version": row.get("agent_context_version"),
            }
            if set(features) != set(DECISION_TIME_FEATURES_V2):
                raise ValueError("V2 schema drift: %s" % sorted(
                    set(features) ^ set(DECISION_TIME_FEATURES_V2)))
            forbidden = set(features) & set(RETROSPECTIVE_OUTCOMES)
            if forbidden:
                raise ValueError(
                    f"outcome leakage in V2 features: {sorted(forbidden)}")
            outcomes: Dict[str, Any] = {
                "forward_return_1d": _num(row.get("forward_return_1d")),
                "forward_return_3d": _num(row.get("forward_return_3d")),
                "mae": _num(row.get("mae")),
                "mfe": _num(row.get("mfe")),
                "hold_return": _num(row.get("hold_return")),
                "opportunity_return": _num(row.get("opportunity_return")),
            }
            fwd3, mfe_ = outcomes["forward_return_3d"], outcomes["mae"]
            outcomes["adverse_forward_3d"] = (
                fwd3 < -ADVERSE_BAND) if fwd3 is not None else None
            outcomes["adverse_mae"] = (
                mfe_ < -ADVERSE_BAND) if mfe_ is not None else None
            rows.append({
                "keys": {
                    "experiment_id": row.get("experiment_id"),
                    "episode_id": row.get("episode_id"),
                    "decision_id": row.get("decision_id"),
                    "decision_timestamp": ts,
                    "attribution_status": row.get("attribution_status"),
                },
                "features": features,
                "outcomes": outcomes,
            })

    missing: Dict[str, int] = {}
    for name in DECISION_TIME_FEATURES_V2:
        missing[name] = sum(1 for r in rows if r["features"].get(name) is None)
    macro_flags = {
        name: {"missing_rate": (missing[name] / len(rows) if rows else None),
               "exceeds_drop_threshold": bool(
                   rows and missing[name] / len(rows)
                   > MACRO_DROP_MISSINGNESS_THRESHOLD)}
        for name in MACRO_FEATURES_V2}
    manifest = {
        "n_rows": len(rows),
        "windows": sorted(set(r["keys"]["experiment_id"] for r in rows)),
        "feature_schema": list(DECISION_TIME_FEATURES_V2),
        "outcome_schema": list(RETROSPECTIVE_OUTCOMES) + [
            "adverse_forward_3d", "adverse_mae"],
        "feature_missingness": missing,
        "macro_drop_review": macro_flags,
        "macro_drop_threshold": MACRO_DROP_MISSINGNESS_THRESHOLD,
        "provenance": FEATURE_PROVENANCE_V2,
        "adverse_band": ADVERSE_BAND,
        "builder": "evaluation/attribution/features_v2.py:build_ml_dataset_v2",
        "source_shas": {rel: sha256_of_file(os.path.join(base_dir, rel))
                        for rel in V2_SOURCE_FILES},
    }
    return {"rows": rows, "manifest": manifest}
