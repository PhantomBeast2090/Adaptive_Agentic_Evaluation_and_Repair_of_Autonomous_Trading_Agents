"""Multi-name synthetic feeds for M-R5 adaptive-repair experiments.

CONTROLLED-KNOWN-MECHANISM benchmarks only. Deterministic frozen price
paths per instrument, explicit episode ranges, portfolio ledger with
5bps costs, affordability clamping recorded. No Indian-market data, no
mining, no discovery claims. Mirrors benchmarks/loss_chasing_power.py
(which stays frozen for M-R4A) generalised to N names plus an optional
synthetic VIX regime series for volatility experiments.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

COST_RATE = 0.0005
NSE_ASSET_ID = "nse_equity"


def make_observation(
    session: int,
    closes: Mapping[str, float],
    cash: float,
    total_equity: float,
    positions: Mapping[str, float],
    vix: float | None = None,
    avg_costs: Mapping[str, float] | None = None,
) -> Dict[str, Any]:
    market = {
        f"{NSE_ASSET_ID}:{name}" if not name.startswith("nse_equity:")
        else name: {
            "status": "AVAILABLE", "values": {"close": price}}
        for name, price in closes.items()
    }
    if vix is not None:
        market["indiavix"] = {
            "status": "AVAILABLE", "values": {"close": vix}}
    first = next(iter(closes.values()))
    unrealized = 0.0
    if avg_costs:
        for name, qty in positions.items():
            base = name.split(":")[0]
            price = closes.get(name, closes.get(base))
            cost = avg_costs.get(name, avg_costs.get(base))
            if price is not None and cost is not None:
                unrealized += qty * (price - cost)
    return {
        "decision_timestamp": f"S{session:04d}",
        "market": market,
        "macro": {},
        "portfolio": {
            "cash": cash,
            "total_equity": total_equity,
            "positions": {
                f"{NSE_ASSET_ID}:{name}": {"quantity": qty}
                for name, qty in positions.items()},
            "holdings_value": sum(positions.values()) * first,
            "exposure": 0.0,
            "unrealized_pnl": unrealized,
        },
        "calendar": {"SYNTH": "OPEN"},
    }


def run_segment(
    agent: Any,
    feed: Mapping[str, List[float]],
    offset: int,
    initial_cash: float,
    vix_series: List[float] | None = None,
) -> Dict[str, Any]:
    """Drive one agent through a multi-name feed segment."""
    agent.reset()
    names = list(feed.keys())
    n_sessions = len(feed[names[0]])
    cash = float(initial_cash)
    holdings = {name: 0.0 for name in names}
    avg_costs = {name: 0.0 for name in names}
    sessions: List[Dict[str, Any]] = []
    peak = float(initial_cash)
    max_drawdown = 0.0
    turnover = 0.0
    clamped = 0
    for local in range(n_sessions):
        session = offset + local
        closes = {name: feed[name][local] for name in names}
        value_before = cash + sum(
            holdings[name] * closes[name] for name in names)
        obs = make_observation(
            session, closes, cash, value_before,
            {n: q for n, q in holdings.items() if q > 0},
            vix_series[local] if vix_series else None,
            {n: c for n, c in avg_costs.items()
             if holdings.get(n, 0.0) > 0})
        orders = [dict(o) for o in agent.act(obs)]
        fills: Dict[str, float] = {}
        for order in orders:
            if order.get("side") != "BUY":
                continue
            instrument = str(order.get("instrument", ""))
            if instrument in closes:
                name, price = instrument, closes[instrument]
            elif instrument.split(":")[0] in closes:
                name = instrument.split(":")[0]
                price = closes[name]
            else:
                continue
            try:
                want = float(order.get("quantity", 0.0))
            except (TypeError, ValueError):
                continue
            if want <= 0:
                continue
            affordable = cash / (price * (1.0 + COST_RATE)) if price > 0 else 0.0
            if want > affordable + 1e-9:
                clamped += 1
            fill = min(want, affordable)
            cost = fill * price * COST_RATE
            cash -= fill * price + cost
            prior_qty = holdings.get(name, 0.0)
            prior_cost = avg_costs.get(name, 0.0)
            holdings[name] = prior_qty + fill
            if holdings[name] > 0:
                avg_costs[name] = (
                    (prior_qty * prior_cost + fill * price)
                    / holdings[name])
            turnover += fill * price
            fills[name] = fills.get(name, 0.0) + fill
        value = cash + sum(holdings[name] * closes[name] for name in names)
        reward = value - value_before
        peak = max(peak, value)
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        sessions.append({
            "session": session,
            "closes": dict(closes),
            "cash": cash,
            "quantities": dict(holdings),
            "value": value,
            "reward": reward,
            "buy_quantity": sum(
                float(o.get("quantity", 0.0)) for o in orders
                if o.get("side") == "BUY"),
            "order_count": len(orders),
            "names_held": sum(1 for q in holdings.values() if q > 0),
            "drawdown": drawdown,
            "unrealized": sum(
                holdings[name] * (closes[name] - avg_costs.get(name, 0.0))
                for name in names if holdings.get(name, 0.0) > 0),
        })
    return {
        "sessions": sessions,
        "final_value": value,
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "clamped_sessions": clamped,
        "n_sessions": n_sessions,
    }


def episode_metric(
    trace_sessions: List[Dict[str, Any]],
    episodes: List[List[int]],
    field: str,
    aggregate: str = "sum",
) -> List[Dict[str, Any]]:
    """Per-episode aggregation of a session field over explicit ranges."""
    by_session = {s["session"]: s for s in trace_sessions}
    out = []
    for start, end in episodes:
        values = [float(by_session[t].get(field, 0.0) or 0.0)
                  for t in range(start, end + 1)]
        total = sum(values)
        out.append({
            "start": start, "end": end,
            "value": total if aggregate == "sum" else max(values),
        })
    return out


def inactivity_rate(trace_sessions: List[Dict[str, Any]]) -> float:
    quiet = sum(1 for s in trace_sessions if s["order_count"] <= 0)
    return quiet / len(trace_sessions) if trace_sessions else 1.0
