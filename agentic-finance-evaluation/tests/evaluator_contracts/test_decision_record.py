"""B. DecisionRecord tests."""

import dataclasses

import pytest

from evaluation.contracts.decision_record import DecisionRecord

PRICE = 2489.25
QTY = 10.0
NOTIONAL = QTY * PRICE
FEE = NOTIONAL * 5.0 / 10000.0
CASH_AFTER = 100000.0 - NOTIONAL - FEE
EQUITY_AFTER = CASH_AFTER + NOTIONAL
REWARD = EQUITY_AFTER - 100000.0


def _record_kwargs(**overrides):
    kwargs = {
        "decision_timestamp": "2023-05-15",
        "state_fingerprint": "state-fp-001",
        "visible_assets": ("nse_equity:RELIANCE:EQ", "nifty50"),
        "unavailable_assets": ("brent",),
        "submitted_orders": (
            {
                "asset_id": "nse_equity",
                "instrument": "RELIANCE:EQ",
                "side": "BUY",
                "quantity": QTY,
            },
        ),
        "validation": ({"status": "VALIDATED"},),
        "executions": (
            {
                "asset_id": "nse_equity",
                "instrument": "nse_equity:RELIANCE:EQ",
                "action_normalized": "BUY",
                "requested_quantity": QTY,
                "executed_quantity": QTY,
                "execution_price": PRICE,
                "transaction_cost": FEE,
                "execution_status": "EXECUTED_FULL",
                "constraint_binding": None,
            },
        ),
        "execution_price": PRICE,
        "transaction_cost": FEE,
        "portfolio_before": {"cash": 100000.0, "total_equity": 100000.0},
        "portfolio_after": {"cash": CASH_AFTER, "total_equity": EQUITY_AFTER},
        "reward": REWARD,
        "environment_metadata": {
            "market_fingerprint": "mfp-001",
            "calendar": {"NSE_CM": "OPEN"},
        },
        "agent_metadata": {"confidence": 0.7, "rationale": "momentum"},
    }
    kwargs.update(overrides)
    return kwargs


def test_valid_record():
    record = DecisionRecord(**_record_kwargs())
    assert record.decision_timestamp == "2023-05-15"
    assert record.reward == pytest.approx(REWARD)
    assert record.fingerprint()


def test_invalid_record_rejected():
    with pytest.raises(ValueError):
        DecisionRecord(**_record_kwargs(decision_timestamp="15-05-2023"))
    with pytest.raises(ValueError):
        DecisionRecord(**_record_kwargs(state_fingerprint=""))
    with pytest.raises(ValueError):
        # Visible/unavailable overlap: an asset cannot be both.
        DecisionRecord(
            **_record_kwargs(
                visible_assets=("brent",),
                unavailable_assets=("brent",),
            )
        )
    with pytest.raises(ValueError):
        # Reward must equal equity delta (environment reward definition).
        DecisionRecord(**_record_kwargs(reward=123.0))
    with pytest.raises(ValueError):
        DecisionRecord(**_record_kwargs(environment_metadata={}))


def test_record_is_immutable_including_nested():
    record = DecisionRecord(**_record_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.reward = 0.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.visible_assets = ()  # type: ignore[misc]
    # Mutating caller-owned inputs after construction has no effect.
    orders = [
        {
            "asset_id": "nse_equity",
            "instrument": "RELIANCE:EQ",
            "side": "BUY",
            "quantity": QTY,
        }
    ]
    record_b = DecisionRecord(**_record_kwargs(submitted_orders=orders))
    orders[0]["side"] = "SELL"
    assert record_b.submitted_orders[0]["side"] == "BUY"
    # List inputs are normalized to tuples.
    assert isinstance(record_b.visible_assets, tuple)
    with pytest.raises(TypeError):
        record_b.submitted_orders[0]["side"] = "SELL"
    with pytest.raises(TypeError):
        record_b.environment_metadata["calendar"]["NSE_CM"] = "CLOSED"


def test_optional_metadata_whitelisted():
    bare = DecisionRecord(**_record_kwargs(agent_metadata=None))
    assert bare.agent_metadata is None
    with pytest.raises(ValueError):
        DecisionRecord(
            **_record_kwargs(agent_metadata={"chain_of_thought": "..."})
        )
    with pytest.raises(ValueError):
        DecisionRecord(**_record_kwargs(agent_metadata={"confidence": 2.0}))


def test_deterministic_serialization_round_trip():
    first = DecisionRecord(**_record_kwargs())
    second = DecisionRecord.from_dict(first.to_dict())
    assert first == second
    assert first.fingerprint() == second.fingerprint()
    # Dictionary ordering does not alter identity.
    reordered = DecisionRecord.from_dict(
        {k: first.to_dict()[k] for k in reversed(list(first.to_dict()))}
    )
    assert reordered.fingerprint() == first.fingerprint()


def test_material_change_alters_fingerprint():
    first = DecisionRecord(**_record_kwargs())
    altered = DecisionRecord(**_record_kwargs(transaction_cost=FEE + 1.0,
                                               reward=REWARD + 1.0,
                                               portfolio_after={
                                                   "cash": CASH_AFTER - 1.0,
                                                   "total_equity": EQUITY_AFTER + 1.0,
                                               }))
    assert altered.fingerprint() != first.fingerprint()
