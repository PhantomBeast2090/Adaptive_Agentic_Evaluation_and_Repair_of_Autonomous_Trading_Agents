import json
from datetime import date

import pandas as pd

from src.india.calendar import NSETradingCalendar
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
