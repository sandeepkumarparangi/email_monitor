from __future__ import annotations

from app.calendar_service import CalendarService
from app.classifier import EmailClassifier
from app.cloud_storage import create_cloud_storage_provider
from app.config import load_config
from app.database import AgentDatabase
from app.gmail_service import GmailService
from app.interview_extractor import InterviewExtractor
from app.logging_utils import configure_logging
from app.processor import EmailAutomationProcessor
from app.scheduler import AgentScheduler


def build_processor() -> EmailAutomationProcessor:
    config = load_config()
    configure_logging(config.log_level)

    db = AgentDatabase(config.database_path)
    db.initialize()

    gmail = GmailService(config)
    classifier = EmailClassifier()
    extractor = InterviewExtractor(
        local_timezone=config.local_timezone,
        default_duration_minutes=config.default_interview_duration_minutes,
    )
    calendar = CalendarService(config)
    cloud = create_cloud_storage_provider(config)

    return EmailAutomationProcessor(
        config=config,
        db=db,
        gmail_service=gmail,
        classifier=classifier,
        extractor=extractor,
        calendar_service=calendar,
        cloud_storage=cloud,
    )


def main() -> None:
    processor = build_processor()
    config = load_config()
    scheduler = AgentScheduler(processor=processor, interval_minutes=config.check_interval_minutes)
    scheduler.start()


if __name__ == "__main__":
    main()

