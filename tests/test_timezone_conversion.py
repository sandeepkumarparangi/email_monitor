from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.interview_extractor import InterviewExtractor


def test_timezone_conversion_to_local():
    dt_et = datetime(2026, 8, 12, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    converted = InterviewExtractor.to_local_timezone(dt_et, "America/Chicago")
    assert converted.hour == 13
    assert converted.tzinfo == ZoneInfo("America/Chicago")

