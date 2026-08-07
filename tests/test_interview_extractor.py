from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.interview_extractor import InterviewExtractor
from app.models import EmailMessageData


def test_interview_extractor_parses_range_and_timezone():
    extractor = InterviewExtractor(local_timezone="America/Chicago")
    email = EmailMessageData(
        gmail_message_id="msg-1",
        thread_id="thread-1",
        sender="Alice Recruiter <alice@acme.com>",
        subject="Interview with Acme for Senior Backend Engineer",
        body=(
            "Hi,\n"
            "We would like to schedule your interview on August 12th from 11:00 AM to 12:00 PM CT.\n"
            "Join Zoom: https://zoom.us/j/123\n"
            "Please prepare system design examples.\n"
        ),
        received_at=datetime(2026, 8, 7, 9, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    details = extractor.extract(email)
    assert details.is_interview
    assert not details.needs_review
    assert details.company is not None
    assert details.interview_start is not None
    assert details.interview_end is not None
    assert details.original_timezone == "America/Chicago"
    assert details.interview_type == "Zoom"


def test_interview_extractor_flags_missing_time():
    extractor = InterviewExtractor(local_timezone="America/Chicago")
    email = EmailMessageData(
        gmail_message_id="msg-2",
        thread_id="thread-2",
        sender="Bob Recruiter <bob@beta.com>",
        subject="Interview Invitation",
        body="We would love to interview you next week. Please share your availability.",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    details = extractor.extract(email)
    assert details.is_interview
    assert details.needs_review
    assert "interview_start" in details.missing_fields

