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


def test_gold_contract_before_first_trade_is_confirmed():
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-01"]),
            "first_trade_date": pd.to_datetime(["2024-01-02"]),
            "expiry_date": pd.to_datetime(["2024-02-01"]),
            "contract_symbol": ["GOLDFEB24"],
        }
    )
    result = LeakageAuditor().check_gold_roll_leakage(frame)
    assert any(v.severity == "CONFIRMED" for v in result)


def test_macro_value_is_not_available_before_release():
    frame = pd.DataFrame(
        {"availability_date": pd.to_datetime(["2024-02-12"])}
    )
    result = LeakageAuditor().check_information_as_of(
        frame, pd.to_datetime(["2024-02-01"])
    )
    assert result[0].severity == "CONFIRMED"


def test_macro_before_release_is_confirmed():
    frame = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-31"]),
            "availability_date": pd.to_datetime(["2024-01-15"]),
        }
    )
    result = LeakageAuditor().check_macro_availability_leakage(frame)
    assert result[0].severity == "CONFIRMED"


def test_processing_fit_on_full_sample_is_confirmed():
    result = LeakageAuditor().check_processing_leakage(
        {"normalization": "fit_on_full_dataset"}
    )
    assert result[0].severity == "CONFIRMED"


def test_leakage_without_datasets_is_not_evaluable():
    report = LeakageAuditor().audit_all()
    assert report.validation_status == "NOT_EVALUABLE"
    assert not report.is_clean


def test_supplied_clean_dataset_is_evaluated():
    report = LeakageAuditor().audit_all(
        price_df=pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    )
    assert report.validation_status == "EVALUATED"
    assert report.is_clean


def test_policy_announcement_can_precede_effective_date():
    report = LeakageAuditor().audit_all(
        policy_df=pd.DataFrame({
            "availability_date": ["2024-02-07"],
            "announcement_timestamp": ["2024-02-07T10:00:00+05:30"],
            "effective_timestamp": ["2024-02-08T00:00:00+05:30"],
        })
    )
    assert report.validation_status == "EVALUATED"
    assert report.is_clean
