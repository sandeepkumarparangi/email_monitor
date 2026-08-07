from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.interview_extractor import InterviewExtractor
from app.models import DownloadedAttachment, EmailMessageData


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
    assert details.action == "availability"


def test_interview_extractor_parses_ics_attachment():
    extractor = InterviewExtractor(local_timezone="America/Chicago")
    email = EmailMessageData(
        gmail_message_id="msg-3",
        thread_id="thread-3",
        sender="Talent Team <talent@acme.com>",
        subject="Updated interview invite",
        body="Please see the attached calendar invite.",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    attachment = DownloadedAttachment(
        filename="invite.ics",
        mime_type="text/calendar",
        content=(
            b"BEGIN:VCALENDAR\r\n"
            b"METHOD:REQUEST\r\n"
            b"BEGIN:VEVENT\r\n"
            b"UID:acme-interview-123\r\n"
            b"SEQUENCE:2\r\n"
            b"DTSTART;TZID=America/New_York:20260812T140000\r\n"
            b"DTEND;TZID=America/New_York:20260812T150000\r\n"
            b"SUMMARY:Interview with Acme for Senior Backend Engineer\r\n"
            b"DESCRIPTION:Join Zoom\\nhttps://zoom.us/j/123\r\n"
            b"LOCATION:Zoom\r\n"
            b"ORGANIZER;CN=Alice Recruiter:mailto:alice@acme.com\r\n"
            b"END:VEVENT\r\n"
            b"END:VCALENDAR\r\n"
        ),
    )

    details = extractor.extract(email, [attachment])

    assert details.is_interview
    assert not details.needs_review
    assert details.calendar_uid == "acme-interview-123"
    assert details.action == "update"
    assert details.company == "Acme"
    assert details.job_title == "Senior Backend Engineer"
    assert details.interview_start is not None
    assert details.interview_start.hour == 13
    assert details.meeting_link == "https://zoom.us/j/123"
