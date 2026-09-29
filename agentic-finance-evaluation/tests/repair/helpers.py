"""Shared fixtures for repair-loop tests: stub E0 agents and observations.

Stubs are deterministic and side-effect-counted so tests can prove the
wrapper calls the base policy exactly once per decision.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping, Sequence

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from evaluation.contracts.agent import AgentIdentity


def make_obs(
    ts="2023-05-15",
    vix=12.0,
    cash=100000.0,
    equity=None,
    positions=None,
    closes=None,
):
    market = {
        "indiavix": {"status": "AVAILABLE", "values": {"close": vix}}
    }
    names = ["YESBANK:EQ", "ICICIBANK:EQ", "RELIANCE:EQ", "SBIN:EQ",
             "INFY:EQ", "TCS:EQ"]
    for name in names:
        close = (closes or {}).get(name, 100.0)
        market[f"nse_equity:{name}"] = {
            "status": "AVAILABLE", "values": {"close": close}
        }
    pos = {
        f"nse_equity:{key}": {"quantity": qty}
        for key, qty in (positions or {}).items()
    }
    total = equity if equity is not None else cash + 1000.0
    return {
        "decision_timestamp": ts,
        "market": market,
        "macro": {},
        "portfolio": {
            "cash": cash,
            "total_equity": total,
            "positions": pos,
            "holdings_value": 1000.0,
            "exposure": 0.01,
            "unrealized_pnl": 0.0,
        },
        "calendar": {"NSE_CM": "OPEN"},
    }


class StubAgent:
    """Deterministic E0 stub: returns fixed orders, counts act calls."""

    def __init__(self, orders, agent_id="stub-agent", version="v1"):
        self._orders = [dict(o) for o in orders]
        self._identity = AgentIdentity(agent_id, version)
        self.calls = 0

    @property
    def identity(self):
        return self._identity

    def reset(self):
        self.calls = 0

    def act(self, observation: Any) -> Sequence[Mapping[str, Any]]:
        self.calls += 1
        return [dict(o) for o in self._orders]


BUY_TWO = (
    {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
     "side": "BUY", "quantity": 2.0},
    {"asset_id": "nse_equity", "instrument": "INFY:EQ",
     "side": "BUY", "quantity": 2.0},
)

BUY_SELL = (
    {"asset_id": "nse_equity", "instrument": "RELIANCE:EQ",
     "side": "BUY", "quantity": 2.0},
    {"asset_id": "nse_equity", "instrument": "TCS:EQ",
     "side": "SELL", "quantity": 1.0},
)


def twin_policy_fingerprint(wrapper, stub_factory, observations):
    """Advance a fresh twin through the same observations; fingerprint it.

    Proves the wrapper never perturbs policy state beyond normal act()
    evolution: the owned copy must match an untouched twin exactly.
    """
    from evaluation.diagnostics.repair.application import fingerprint_agent

    twin = stub_factory()
    for obs in observations:
        twin.act(obs)
    return fingerprint_agent(twin, twin.identity)


def make_mechanism(taxonomy="turnover", mechanism_id="mech-001",
                   trigger_hint=(), scope_hint=None):
    from evaluation.repair.schemas import FailureMechanism

    return FailureMechanism(
        mechanism_id=mechanism_id,
        taxonomy=taxonomy,
        condition=("exposure=high",),
        scope_hint=dict(scope_hint or {}),
        trigger_hint=tuple(trigger_hint),
        evidence_refs=("eval-001",),
        provenance={"test": "fixture", "evaluation_id": "eval-001"},
    )


def make_entry(entry_id="mem-001", agent_id="stub-agent", spec=None,
               sequence=1, priority=0):
    from evaluation.repair.schemas import MemoryEntry

    assert spec is not None
    return MemoryEntry(
        entry_id=entry_id,
        agent_id=agent_id,
        spec=spec,
        source_evaluation_id="eval-001",
        diagnostic_evidence=("eval-001:pattern",),
        priority=priority,
        sequence=sequence,
        provenance={
            "mechanism_fingerprint": spec.mechanism_fingerprint,
            "candidate_fingerprint": "test-only",
        },
    )
