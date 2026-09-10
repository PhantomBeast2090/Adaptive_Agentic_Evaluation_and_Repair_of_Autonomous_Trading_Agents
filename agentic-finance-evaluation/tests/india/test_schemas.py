from datetime import date

import pytest
from pydantic import ValidationError

from src.schemas.india_data import (
    IndianEquityRecord,
    IndianGoldFuturesRecord,
    IndianMacroRecord,
    RBIPolicyRecord,
)


def test_macro_rejects_pre_release_value():
    with pytest.raises(ValidationError):
        IndianMacroRecord(
            observation_date=date(2024, 1, 31),
            availability_date=date(2024, 1, 15),
            variable="CPI",
            value=5.1,
            source="MOSPI",
        )


def test_policy_allows_announcement_before_effective_date():
    record = RBIPolicyRecord(
        observation_date=date(2024, 6, 7),
        availability_date=date(2024, 6, 6),
        rate_type="REPO",
        rate_pct=6.5,
    )
    assert record.availability_date < record.observation_date


def test_equity_does_not_invent_adjusted_close():
    record = IndianEquityRecord(
        date=date(2024, 1, 2), symbol="TEST", close=100
    )
    assert record.adjusted_close is None
    assert record.corporate_action_adjusted is False


def test_gold_contract_expiry_must_not_precede_trade():
    with pytest.raises(ValidationError):
        IndianGoldFuturesRecord(
            trade_date=date(2024, 1, 10),
            contract_symbol="GOLDJAN24",
            expiry_date=date(2024, 1, 9),
            close=60000,
        )
