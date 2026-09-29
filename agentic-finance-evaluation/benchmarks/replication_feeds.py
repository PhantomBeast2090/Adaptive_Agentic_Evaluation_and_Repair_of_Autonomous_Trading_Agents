"""Four-window replication feeds (M-R4A-R1, additive).

FINAL FOUR-WINDOW REPLICATION / GENERALISATION STUDY for the frozen
admitted M-R4A repair (mem-MR4A, max_quantity 5.0). NOT a new repair
mechanism: the repair, cap, agent, compiler, and gates are unchanged.

Four structurally different deterministic price paths (explicit unit
patterns, no RNG): different start prices, calm lengths, decline
magnitudes, episode counts/positions, recovery patterns, and orderings.
Episode ranges are derived mechanically (maximal decline runs) from the
frozen formulas and recorded in the pre-registered protocol. Base-only
structural QA (episodes exist, counters reset, cash never binds) precedes
any repaired run; repaired results never feed back into window design.
"""

from __future__ import annotations

from typing import Dict, List

COST_RATE = 0.0005
NORMAL_QUANTITY = 5.0
CASH_MULTIPLE = 5000.0

WINDOWS: Dict[str, Dict[str, object]] = {
    # W1 resembles the original M-R4A structure (12-session sawtooth).
    "W1": {
        "start_price": 100.0,
        "unit": (0.004, 0.004, -0.015, -0.015, -0.015, 0.003, 0.003,
                 0.003, -0.02, -0.02, 0.003, 0.003),
        "n_blocks": 8,
    },
    # W2: decline-first ordering, deeper longer declines, long calm tail.
    "W2": {
        "start_price": 250.0,
        "unit": (-0.01, -0.01, 0.005, 0.005, 0.005, -0.025, -0.025,
                 -0.025, -0.025, 0.005, 0.005, 0.005, 0.005, 0.005),
        "n_blocks": 6,
    },
    # W3: frequent shallow declines, short calms, low price level.
    "W3": {
        "start_price": 50.0,
        "unit": (-0.01, -0.01, 0.004, 0.004, -0.01, -0.01, 0.004, 0.004),
        "n_blocks": 10,
    },
    # W4: mixed magnitudes with strong recoveries (rebound economics).
    "W4": {
        "start_price": 1000.0,
        "unit": (0.005, 0.005, 0.005, 0.005, -0.03, -0.03, 0.015, 0.015,
                 -0.01, -0.01, -0.01, -0.01, 0.005, 0.005, 0.005, 0.005),
        "n_blocks": 6,
    },
}


def generate_closes(window: str) -> List[float]:
    """Deterministic frozen feed for one window; pure function of spec."""
    spec = WINDOWS[window]
    prices: List[float] = []
    price = float(spec["start_price"])  # type: ignore[arg-type]
    for _ in range(int(spec["n_blocks"])):  # type: ignore[arg-type]
        for ret in spec["unit"]:  # type: ignore[union-attr]
            price *= (1.0 + float(ret))
            prices.append(round(price, 4))
    return prices


def initial_cash(window: str) -> float:
    """Pre-registered rule: cash = 5000 x start price (structural, blind)."""
    return CASH_MULTIPLE * float(WINDOWS[window]["start_price"])  # type: ignore[arg-type]


def episode_ranges(window: str) -> List[List[int]]:
    """Maximal decline runs, derived mechanically from the frozen feed."""
    prices = generate_closes(window)
    episodes: List[List[int]] = []
    index, total = 0, len(prices)
    while index < total - 1:
        if prices[index + 1] < prices[index]:
            end = index
            while end + 1 < total and prices[end + 1] < prices[end]:
                end += 1
            episodes.append([index, end])
            index = end + 1
        else:
            index += 1
    return episodes


def describe(window: str) -> Dict[str, object]:
    """Frozen window specification record for the protocol manifest."""
    closes = generate_closes(window)
    return {
        "start_price": WINDOWS[window]["start_price"],
        "unit": list(WINDOWS[window]["unit"]),  # type: ignore[arg-type]
        "n_blocks": WINDOWS[window]["n_blocks"],
        "n_sessions": len(closes),
        "initial_cash": initial_cash(window),
        "cost_bps": COST_RATE * 10000.0,
        "episodes": episode_ranges(window),
        "n_episodes": len(episode_ranges(window)),
        "feed_fingerprint": __feed_fp(window),
    }


def __feed_fp(window: str) -> str:
    import hashlib
    import json

    return hashlib.sha256(json.dumps(
        {"unit": list(WINDOWS[window]["unit"]),  # type: ignore[arg-type]
         "start": WINDOWS[window]["start_price"],
         "blocks": WINDOWS[window]["n_blocks"],
         "closes": generate_closes(window)},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
