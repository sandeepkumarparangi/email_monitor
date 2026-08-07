from __future__ import annotations

import argparse
import json

from app.calendar_service import CalendarService
from app.classifier import EmailClassifier
from app.cloud_storage import create_cloud_storage_provider
from app.config import AppConfig, load_config
from app.database import AgentDatabase
from app.gmail_service import GmailService
from app.interview_extractor import InterviewExtractor
from app.logging_utils import configure_logging
from app.processor import EmailAutomationProcessor
from app.runtime_server import serve_web_runtime
from app.scheduler import AgentScheduler


def build_processor(config: AppConfig | None = None) -> EmailAutomationProcessor:
    config = config or load_config()
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI email monitoring and automation agent")
    parser.add_argument(
        "--mode",
        choices=("worker", "web", "healthcheck"),
        help="Override APP_RUNTIME_MODE for this invocation.",
    )
    return parser.parse_args()


def run_healthcheck(config: AppConfig) -> dict[str, object]:
    db = AgentDatabase(config.database_path)
    db.initialize()
    snapshot = db.get_dashboard_snapshot(limit=1)
    return {
        "status": "ok",
        "database_path": config.database_path,
        "counts": snapshot.get("counts", {}),
    }


def main() -> None:
    config = load_config()
    configure_logging(config.log_level)
    args = parse_args()
    mode = (args.mode or config.runtime_mode).strip().lower()

    if mode == "healthcheck":
        print(json.dumps(run_healthcheck(config), ensure_ascii=True))
        return

    processor = build_processor(config)
    if mode == "web":
        serve_web_runtime(
            processor=processor,
            bind_host=config.bind_host,
            port=config.port,
            dashboard_page_size=config.dashboard_page_size,
            interval_minutes=config.check_interval_minutes,
        )
        return

    scheduler = AgentScheduler(processor=processor, interval_minutes=config.check_interval_minutes)
    scheduler.start()


if __name__ == "__main__":
    main()
