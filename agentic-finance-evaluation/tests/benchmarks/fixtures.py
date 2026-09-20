"""Hand-built observation builders for benchmark contract tests.

No market episodes: observations are plain mappings carrying the closed
observation schema (decision_timestamp, market, macro, portfolio,
calendar). A ``vix`` of None means the indiavix slot is non-AVAILABLE;
the string "absent" drops the slot entirely.
"""

STATUS_AVAILABLE = "AVAILABLE"


def make_obs(vix="MISSING", cash=100000.0, positions=None, day="2023-05-16"):
    market = {}
    if vix != "absent":
        if vix is None or vix == "MISSING":
            market["indiavix"] = {"status": "OBS_MISSING", "values": {}}
        elif vix == "nonnumeric":
            market["indiavix"] = {
                "status": STATUS_AVAILABLE,
                "venue": "NSE_CM",
                "observation_date": "2023-05-15",
                "availability_date": None,
                "vintage": None,
                "values": {"close": "high"},
                "reason": "x",
            }
        else:
            market["indiavix"] = {
                "status": STATUS_AVAILABLE,
                "venue": "NSE_CM",
                "observation_date": "2023-05-15",
                "availability_date": None,
                "vintage": None,
                "values": {"close": float(vix)},
                "reason": "x",
            }
    position_block = {}
    for key, quantity in dict(positions or {}).items():
        position_block[key] = {"quantity": quantity, "avg_cost": 100.0}
    return {
        "decision_timestamp": day,
        "market": market,
        "macro": {},
        "portfolio": {
            "cash": cash,
            "total_equity": cash,
            "holdings_value": 0.0,
            "positions": position_block,
        },
        "calendar": {"NSE_CM": "OPEN"},
    }


class FakeObservation:
    """Minimal TargetObservation-shaped object (to_dict entry point)."""

    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)
