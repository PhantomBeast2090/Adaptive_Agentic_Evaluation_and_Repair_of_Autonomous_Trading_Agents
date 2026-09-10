import pandas as pd

from src.india.coverage_audit import audit_availability_consistency


def test_release_date_after_observation_is_valid():
    frame = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-31"]),
            "availability_date": pd.to_datetime(["2024-02-12"]),
        }
    )
    result = audit_availability_consistency(frame)
    assert result.violations == 0


def test_release_date_before_observation_is_reported():
    frame = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-31"]),
            "availability_date": pd.to_datetime(["2024-01-15"]),
        }
    )
    result = audit_availability_consistency(frame)
    assert result.violations == 1
    assert result.violation_examples
