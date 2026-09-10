import pandas as pd
import pytest

from src.india.information_set import InformationSet


def test_latest_released_vintage_is_selected_point_in_time():
    vintages = pd.DataFrame(
        {
            "variable": ["CPI", "CPI", "CPI"],
            "observation_date": ["2024-01-31"] * 3,
            "availability_date": ["2024-02-12", "2024-03-12", "2024-02-12"],
            "revision_version": [0, 1, 2],
            "value": [100.0, 101.0, 100.5],
        }
    )
    info = InformationSet(vintages)
    before_release = info.information_available_at("2024-02-11")
    assert before_release.empty
    as_of_march = info.information_available_at("2024-03-13")
    assert as_of_march.iloc[0]["value"] == 101.0


def test_vintage_cannot_be_available_before_observation_date():
    with pytest.raises(ValueError):
        InformationSet(pd.DataFrame({
            "variable": ["CPI"],
            "observation_date": ["2024-01-31"],
            "availability_date": ["2024-01-01"],
            "revision_version": [0],
        }))


def test_vintages_are_selected_by_release_timestamp():
    vintages = pd.DataFrame(
        {
            "variable": ["CPI"] * 3,
            "observation_date": ["2024-01-31"] * 3,
            "availability_timestamp": [
                "2024-02-10T09:00:00Z",
                "2024-03-10T09:00:00Z",
                "2024-04-10T09:00:00Z",
            ],
            "revision_version": [0, 1, 2],
            "value": [100.0, 101.0, 102.0],
        }
    )
    info = InformationSet(vintages)
    assert info.information_available_at("2024-02-20").iloc[0]["value"] == 100.0
    assert info.information_available_at("2024-03-20").iloc[0]["value"] == 101.0
    assert info.information_available_at("2024-04-20").iloc[0]["value"] == 102.0


def test_missing_release_timing_is_rejected():
    with pytest.raises(ValueError, match="reliable availability"):
        InformationSet(pd.DataFrame({
            "variable": ["CPI"],
            "observation_date": ["2024-01-31"],
            "availability_date": [None],
            "revision_version": [0],
        }))
