from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.classifier import EmailClassifier
from app.cloud_storage import LocalCloudStorageProvider
from app.database import AgentDatabase
from app.interview_extractor import InterviewExtractor
from app.models import DownloadedAttachment, EmailMessageData, InterviewDetails
from app.processor import EmailAutomationProcessor
from tests.fakes import FakeCalendarService, FakeGmailService


def _message(message_id: str, thread_id: str, body: str) -> EmailMessageData:
    return EmailMessageData(
        gmail_message_id=message_id,
        thread_id=thread_id,
        sender="Recruiter <recruiter@acme.com>",
        subject="Interview with Acme for Staff Engineer",
        body=body,
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )


def test_end_to_end_mock_workflow(app_config):
    db = AgentDatabase(app_config.database_path)
    db.initialize()

    message_1 = _message(
        "m1",
        "thread-1",
        "Interview on August 12th from 11:00 AM to 12:00 PM CT. Join https://zoom.us/j/123",
    )
    message_2 = _message(
        "m2",
        "thread-1",
        "Updated interview schedule: August 12th from 1:00 PM to 2:00 PM CT. Join https://zoom.us/j/123",
    )

    gmail = FakeGmailService(
        emails={"m1": message_1, "m2": message_2},
        attachments={"m1": [DownloadedAttachment(filename="JD.pdf", mime_type="application/pdf", content=b"data")]},
    )
    calendar = FakeCalendarService()
    processor = EmailAutomationProcessor(
        config=app_config,
        db=db,
        gmail_service=gmail,
        classifier=EmailClassifier(),
        extractor=InterviewExtractor(local_timezone=app_config.local_timezone),
        calendar_service=calendar,
        cloud_storage=LocalCloudStorageProvider(app_config.local_backup_dir),
    )

    processor.run_once()

    assert db.is_processed("m1")
    assert db.is_processed("m2")
    assert calendar.created_count == 1
    assert calendar.updated_count == 1
    assert app_config.processed_marker_label in gmail.applied_labels["m1"]
    assert app_config.processed_marker_label in gmail.applied_labels["m2"]


def test_workflow_updates_existing_event_from_new_thread_via_ics(app_config):
    db = AgentDatabase(app_config.database_path)
    db.initialize()

    initial_message = _message(
        "m-initial",
        "thread-1",
        "Interview on August 12th from 11:00 AM to 12:00 PM CT. Join https://zoom.us/j/abc",
    )
    update_message = EmailMessageData(
        gmail_message_id="m-update",
        thread_id="thread-2",
        sender="Recruiter <recruiter@acme.com>",
        subject="Updated interview invite for Acme",
        body="Attached is the updated calendar invite.",
        received_at=datetime(2026, 8, 7, 11, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )

    gmail = FakeGmailService(
        emails={"m-initial": initial_message, "m-update": update_message},
        attachments={
            "m-update": [
                DownloadedAttachment(
                    filename="invite.ics",
                    mime_type="text/calendar",
                    content=(
                        b"BEGIN:VCALENDAR\r\n"
                        b"METHOD:REQUEST\r\n"
                        b"BEGIN:VEVENT\r\n"
                        b"UID:acme-uid-123\r\n"
                        b"SEQUENCE:1\r\n"
                        b"DTSTART;TZID=America/Chicago:20260812T130000\r\n"
                        b"DTEND;TZID=America/Chicago:20260812T140000\r\n"
                        b"SUMMARY:Interview with Acme for Staff Engineer\r\n"
                        b"DESCRIPTION:Join Zoom\\nhttps://zoom.us/j/abc\r\n"
                        b"LOCATION:Zoom\r\n"
                        b"END:VEVENT\r\n"
                        b"END:VCALENDAR\r\n"
                    ),
                )
            ]
        },
    )
    calendar = FakeCalendarService()
    processor = EmailAutomationProcessor(
        config=app_config,
        db=db,
        gmail_service=gmail,
        classifier=EmailClassifier(),
        extractor=InterviewExtractor(local_timezone=app_config.local_timezone),
        calendar_service=calendar,
        cloud_storage=LocalCloudStorageProvider(app_config.local_backup_dir),
    )

    processor.run_once()

    assert calendar.created_count == 1
    assert calendar.updated_count == 1
    assert calendar.events["evt-1"]["calendar_uid"] == "acme-uid-123"


def test_reprocess_message_resets_processed_needs_review_and_schedules(app_config):
    db = AgentDatabase(app_config.database_path)
    db.initialize()

    email = EmailMessageData(
        gmail_message_id="oracle-1",
        thread_id="thread-oracle",
        sender="Oracle Talent Acquisition <ota-scheduling_ww@oracle.com>",
        subject="Oracle Interview for the position 337023 Principal Software Engineer",
        body=(
            "We are pleased to confirm that your interview is scheduled for Mon, 10 Aug, 2026 at 02:30 PM America/Chicago.\n"
            "Interview Duration 60 minutes\n"
            "Click here to join the meeting: https://oracle.zoom.us/j/97556824486?pwd=abc\n"
        ),
        received_at=datetime(2026, 8, 7, 14, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    gmail = FakeGmailService(emails={"oracle-1": email})
    calendar = FakeCalendarService()
    processor = EmailAutomationProcessor(
        config=app_config,
        db=db,
        gmail_service=gmail,
        classifier=EmailClassifier(),
        extractor=InterviewExtractor(local_timezone=app_config.local_timezone),
        calendar_service=calendar,
        cloud_storage=LocalCloudStorageProvider(app_config.local_backup_dir),
    )

    db.upsert_email_received(email)
    db.mark_processed("oracle-1", "Interview / Interview Invitation")
    db.upsert_interview(
        email=email,
        details=InterviewDetails(
            is_interview=True,
            needs_review=True,
            missing_fields=["job_title"],
            action="schedule",
            company="Oracle",
            review_reason="Missing fields: job_title",
        ),
        status="needs_review",
        calendar_event_id=None,
        cloud_backup_path=None,
    )

    processor.reprocess_message("oracle-1")

    assert db.is_processed("oracle-1")
    assert calendar.created_count == 1
    snapshot = db.get_dashboard_snapshot(limit=10)
    assert snapshot["counts"]["needs_review_count"] == 0
