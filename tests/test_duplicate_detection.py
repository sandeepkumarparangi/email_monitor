from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.classifier import EmailClassifier
from app.cloud_storage import LocalCloudStorageProvider
from app.database import AgentDatabase
from app.interview_extractor import InterviewExtractor
from app.models import EmailMessageData
from app.processor import EmailAutomationProcessor
from tests.fakes import FakeCalendarService, FakeGmailService


def test_processor_is_idempotent(app_config):
    db = AgentDatabase(app_config.database_path)
    db.initialize()
    email = EmailMessageData(
        gmail_message_id="m1",
        thread_id="t1",
        sender="Recruiter <recruiter@acme.com>",
        subject="Interview with Acme for Engineer",
        body="Interview on August 12th from 11:00 AM to 12:00 PM CT via https://zoom.us/j/1",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    gmail = FakeGmailService(emails={"m1": email})
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
    processor.run_once()

    assert calendar.created_count == 1
    assert calendar.updated_count == 0

