import json
from datetime import date

import pandas as pd

from src.india.calendar import NSETradingCalendar, load_calendar_directory
from src.india.coverage_audit import audit_calendar_consistency


def test_nse_calendar_uses_explicit_movable_holiday_dates(tmp_path):
    path = tmp_path / "nse.json"
    path.write_text(json.dumps({"CBM": [
        {"tradingDate": "14-Jan-2026"},
        {"tradingDate": "03-Mar-2026"},
    ]}))
    calendar = NSETradingCalendar.from_nse_json(path)
    frame = pd.DataFrame({"date": pd.to_datetime(["2026-03-03", "2026-03-04"])})
    result = audit_calendar_consistency(frame, "date", calendar=calendar)
    assert result.calendar_available is True
    assert result.non_trading_day_observations == 1
    assert date(2026, 3, 3) not in result.missing_dates


def test_nested_category_rows_are_not_duplicate_events(tmp_path):
    path = tmp_path / "nse.json"
    path.write_text(json.dumps({
        "CBM": [{"tradingDate": "03-Mar-2026", "description": "Holi"}],
        "CM": [{"tradingDate": "03-Mar-2026", "description": "Holi"}],
    }))
    calendar = NSETradingCalendar.from_nse_json(path)
    assert len(calendar.events) == 2
    assert len({(event.market_segment, event.trading_date) for event in calendar.events}) == 2


def test_calendar_directory_combines_only_available_years(tmp_path):
    (tmp_path / "nse_trading_holidays_2025.json").write_text(
        json.dumps({"CM": [{"tradingDate": "26-Feb-2025"}]})
    )
    (tmp_path / "nse_trading_holidays_2026.json").write_text(
        json.dumps({"CM": [{"tradingDate": "03-Mar-2026"}]})
    )
    calendar = load_calendar_directory(tmp_path)
    assert calendar is not None
    assert calendar.coverage.covered_years == (2025, 2026)
