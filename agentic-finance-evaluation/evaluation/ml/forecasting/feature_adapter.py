"""PIT-safe forecast context assembly (univariate-first).

Reuses the frozen V2 equity loaders (same CSVs, same strict-`<T`
semantics) — no new market-data pipeline. Context = up to
FORECAST_CONTEXT_LENGTH closes strictly before T for the decision
instrument. Short history is preserved as missingness (caller records
an UNAVAILABLE forecast), never padded or imputed.
"""

from __future__ import annotations

from typing import Any, Dict, List

from evaluation.attribution import features_v2 as F2
from evaluation.ml.forecasting.base import (
    FORECAST_CONTEXT_LENGTH, context_fingerprint,
)


def build_context(instrument: str, decision_timestamp: str,
                  base_dir: str = ".") -> Dict[str, Any]:
    """Assemble the exact PIT input for one (instrument, T) forecast."""
    symbol = str(instrument or "").split(":")[0]
    equity = F2._load_equity(base_dir)
    leg = equity.get(symbol, {"close": []})["close"]
    eligible = [(d, v) for d, v in leg if d < decision_timestamp]
    window = eligible[-FORECAST_CONTEXT_LENGTH:]
    if len(window) < 2:
        raise ValueError(
            f"insufficient PIT history for {symbol} before "
            f"{decision_timestamp} ({len(window)} bars)")
    closes: List[float] = [v for _, v in window]
    stamps: List[str] = [d for d, _ in window]
    series = {"close": closes}
    stamp_map = {"close": stamps}
    return {"series": series, "stamps": stamp_map,
            "reference_level": closes[-1],
            "context_fingerprint": context_fingerprint(series, stamp_map),
            "n_bars": len(closes),
            "full_history_available": len(eligible) >= FORECAST_CONTEXT_LENGTH}
