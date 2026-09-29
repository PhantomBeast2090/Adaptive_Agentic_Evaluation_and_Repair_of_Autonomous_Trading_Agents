"""Loss-chasing POWER benchmark v1.1 (M-R4A, additive).

CONTROLLED-KNOWN-MECHANISM: synthetic deterministic feed + episode
structure for controlled causal testing of the max_quantity repair.
Explicitly NOT natural-market evidence: no Indian data, no mining, no
discovery claim. Reuses the frozen loss-chasing-benchmark@1.0 agent
class (deterministic escalation) and the M-R1 wrapper/compiler/gate
machinery.

Feed (frozen formula, pre-registered): 12-session repeat unit
  [+0.4%, +0.4%, -1.5%x3, +0.3%x3, -2.0%x2, +0.3%x2]
from 100.0; 8 diagnostic blocks (96 sessions, 16 episodes) + 4 held-out
blocks (48 sessions, 8 episodes). Episode ranges are explicit index
pairs (maximal decline runs from the formula). Ledger: cash + qty*price
with 5 bps buy costs; rewards = value change; affordability clamping
recorded (no validity violations possible by construction).

Episode independence: decline runs separated by >=2 calm sessions;
base-only QA shows the loss counter resets after every episode and cash
never binds, so episodes are distinct escalation opportunities on a
shared exogenous path (paired per-episode analysis, never pooled-timesteps).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

UNIT_RETURNS = (0.004, 0.004, -0.015, -0.015, -0.015, 0.003, 0.003, 0.003,
                -0.02, -0.02, 0.003, 0.003)
START_PRICE = 100.0
COST_RATE = 0.0005
INITIAL_CASH = 500000.0
NORMAL_QUANTITY = 5.0
DIAG_BLOCKS = 8
HELD_BLOCKS = 4
NSE_ASSET_ID = "nse_equity"
INSTRUMENT = "RELIANCE:EQ"


def generate_closes(n_blocks: int, start: float = START_PRICE) -> List[float]:
    """Deterministic frozen feed; pure function of block count."""
    prices: List[float] = []
    price = float(start)
    for _ in range(n_blocks):
        for ret in UNIT_RETURNS:
            price *= (1.0 + ret)
            prices.append(round(price, 4))
    return prices


def episode_ranges(n_blocks: int, offset: int = 0,
                   start: float = START_PRICE) -> List[List[int]]:
    """Maximal decline runs, derived mechanically from the frozen feed."""
    prices = generate_closes(n_blocks, start)
    episodes: List[List[int]] = []
    index, total = 0, len(prices)
    while index < total - 1:
        if prices[index + 1] < prices[index]:
            end = index
            while end + 1 < total and prices[end + 1] < prices[end]:
                end += 1
            episodes.append([offset + index, offset + end])
            index = end + 1
        else:
            index += 1
    return episodes


def make_observation(session: int, close: float, cash: float,
                     total_equity: float, positions: Mapping[str, float]
                     ) -> Dict[str, Any]:
    holdings = sum(positions.values())
    return {
        "decision_timestamp": f"S{session:04d}",
        "market": {
            "nse_equity:RELIANCE:EQ": {
                "status": "AVAILABLE", "values": {"close": close}}},
        "macro": {},
        "portfolio": {
            "cash": cash,
            "total_equity": total_equity,
            "positions": {
                f"{NSE_ASSET_ID}:{name}": {"quantity": qty}
                for name, qty in positions.items()},
            "holdings_value": holdings * close,
            "exposure": 0.0,
            "unrealized_pnl": 0.0,
        },
        "calendar": {"SYNTH": "OPEN"},
    }


def run_segment(agent: Any, closes: List[float], offset: int,
                initial_cash: float = INITIAL_CASH) -> Dict[str, Any]:
    """Drive one agent through a feed segment; return full session trace."""
    agent.reset()
    cash, qty = float(initial_cash), 0.0
    sessions: List[Dict[str, Any]] = []
    peak = float(initial_cash)
    max_drawdown = 0.0
    turnover = 0.0
    clamped = 0
    for local, close in enumerate(closes):
        session = offset + local
        total_equity = cash + qty * close
        obs = make_observation(session, close, cash, total_equity,
                               {"RELIANCE:EQ": qty} if qty > 0 else {})
        orders = [dict(o) for o in agent.act(obs)]
        buy_qty = sum(float(o.get("quantity", 0.0)) for o in orders
                      if o.get("side") == "BUY")
        affordable = cash / (close * (1.0 + COST_RATE)) if close > 0 else 0.0
        if buy_qty > affordable + 1e-9:
            clamped += 1
        fill = min(buy_qty, affordable)
        cost = fill * close * COST_RATE
        cash -= fill * close + cost
        qty += fill
        turnover += fill * close
        value = cash + qty * close
        reward = value - total_equity
        peak = max(peak, value)
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        sessions.append({
            "session": session, "close": close, "cash": cash,
            "quantity": qty, "value": value, "reward": reward,
            "buy_quantity": buy_qty, "filled": fill,
            "drawdown": drawdown,
        })
    return {
        "sessions": sessions,
        "final_value": cash + qty * closes[-1],
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "clamped_sessions": clamped,
        "n_sessions": len(closes),
    }


def episode_excess(trace_sessions: List[Dict[str, Any]],
                   episodes: List[List[int]],
                   normal_qty: float = NORMAL_QUANTITY) -> List[Dict[str, Any]]:
    """Per-episode total excess BUY quantity over the normal size."""
    by_session = {s["session"]: s for s in trace_sessions}
    out = []
    for start, end in episodes:
        excess = sum(max(0.0, by_session[t]["buy_quantity"] - normal_qty)
                     for t in range(start, end + 1))
        out.append({"start": start, "end": end, "excess": excess})
    return out


def inactivity_rate(trace_sessions: List[Dict[str, Any]]) -> float:
    quiet = sum(1 for s in trace_sessions if s["buy_quantity"] <= 0)
    return quiet / len(trace_sessions) if trace_sessions else 1.0
