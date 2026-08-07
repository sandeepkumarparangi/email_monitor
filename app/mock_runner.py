from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.classifier import EmailClassifier
from app.cloud_storage import LocalCloudStorageProvider
from app.config import load_config
from app.database import AgentDatabase
from app.interview_extractor import InterviewExtractor
from app.logging_utils import configure_logging
from app.models import EmailMessageData
from app.processor import EmailAutomationProcessor
from tests.fakes import FakeCalendarService, FakeGmailService


def run_mock_workflow() -> None:
    config = load_config()
    configure_logging(config.log_level)
    db = AgentDatabase(config.database_path)
    db.initialize()

    fixture = Path("tests/mock_emails.json")
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    emails = {}
    for item in raw:
        emails[item["gmail_message_id"]] = EmailMessageData(
            gmail_message_id=item["gmail_message_id"],
            thread_id=item["thread_id"],
            sender=item["sender"],
            subject=item["subject"],
            body=item["body"],
            received_at=datetime.fromisoformat(item["received_at"]),
            internal_date_ms=0,
        )

    processor = EmailAutomationProcessor(
        config=config,
        db=db,
        gmail_service=FakeGmailService(emails=emails),
        classifier=EmailClassifier(),
        extractor=InterviewExtractor(local_timezone=config.local_timezone),
        calendar_service=FakeCalendarService(),
        cloud_storage=LocalCloudStorageProvider(config.local_backup_dir),
    )
    processor.run_once()


if __name__ == "__main__":
    run_mock_workflow()

