from datetime import date

import pandas as pd

from src.india.leakage_audit import LeakageAuditor


def test_future_price_column_and_shift_are_detected():
    frame = pd.DataFrame(
        {
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "next_close": [101.0, 102.0, 103.0, 104.0, 105.0, None],
        }
    )
    violations = LeakageAuditor().check_future_price_leakage(frame)
    assert any(v.severity == "POTENTIAL" for v in violations)
    assert any(v.severity == "CONFIRMED" for v in violations)


def test_split_overlap_is_confirmed():
    result = LeakageAuditor().check_split_contamination(
        {
            "context": (date(2020, 1, 1), date(2020, 12, 31)),
            "discovery": (date(2020, 12, 31), date(2021, 12, 31)),
        }
    )
    assert result[0].severity == "CONFIRMED"


def test_gold_contract_data_without_roll_is_mitigated():
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-01"]),
            "expiry_date": pd.to_datetime(["2024-02-01"]),
            "contract_symbol": ["GOLDFEB24"],
        }
    )
    result = LeakageAuditor().check_gold_roll_leakage(frame)
    assert any(v.severity == "MITIGATED" for v in result)


def test_macro_before_release_is_confirmed():
    frame = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-31"]),
            "availability_date": pd.to_datetime(["2024-01-15"]),
        }
    )
    result = LeakageAuditor().check_macro_availability_leakage(frame)
    assert result[0].severity == "CONFIRMED"
