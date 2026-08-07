from __future__ import annotations

import logging
from typing import List

from app.calendar_service import CalendarService
from app.classifier import EmailClassifier
from app.cloud_storage import CloudStorageProvider
from app.config import AppConfig
from app.database import AgentDatabase
from app.gmail_service import GmailService
from app.interview_extractor import InterviewExtractor


LOGGER = logging.getLogger(__name__)


class EmailAutomationProcessor:
    def __init__(
        self,
        config: AppConfig,
        db: AgentDatabase,
        gmail_service: GmailService,
        classifier: EmailClassifier,
        extractor: InterviewExtractor,
        calendar_service: CalendarService,
        cloud_storage: CloudStorageProvider,
    ) -> None:
        self.config = config
        self.db = db
        self.gmail = gmail_service
        self.classifier = classifier
        self.extractor = extractor
        self.calendar = calendar_service
        self.cloud_storage = cloud_storage

    def _all_labels(self) -> List[str]:
        labels = list(EmailClassifier.LABEL_MAP.values())
        labels.append(self.config.processed_marker_label)
        return sorted(set(labels))

    def run_once(self) -> None:
        self.gmail.ensure_labels(self._all_labels())
        message_ids = self.gmail.list_message_ids()
        LOGGER.info("Fetched messages", extra={"status": "start", "count": len(message_ids)})
        for message_id in message_ids:
            try:
                if self.db.is_processed(message_id):
                    continue
                self._process_message(message_id)
            except Exception as exc:
                LOGGER.exception("Message processing failed", extra={"gmail_message_id": message_id, "status": "failed"})
                self.db.mark_failed(message_id, str(exc))

    def _process_message(self, message_id: str) -> None:
        message = self.gmail.get_message(message_id)
        self.db.upsert_email_received(message)
        classification = self.classifier.classify(message)
        labels = [classification.label]

        interview_status = None
        calendar_event_id = None
        backup_path = None
        details = None

        if classification.category in {
            "Interview / Interview Invitation",
            "Assessment / HackerRank / Coding Test",
            "Recruiter / Job Opportunity",
        }:
            details = self.extractor.extract(message)
            if details.is_interview:
                if details.needs_review:
                    interview_status = "needs_review"
                    labels.append(EmailClassifier.LABEL_MAP["Interview - Needs Review"])
                else:
                    attachments = self.gmail.download_attachments(message)
                    existing_event_id = self._resolve_event_id(message, details)
                    if existing_event_id:
                        calendar_event_id = self.calendar.update_event(existing_event_id, details, message)
                        interview_status = "updated"
                    else:
                        calendar_event_id = self.calendar.create_event(details, message)
                        interview_status = "scheduled"
                    backup_path = self.cloud_storage.backup_interview(details, message, attachments)

        labels.append(self.config.processed_marker_label)
        self.gmail.apply_labels(message.gmail_message_id, sorted(set(labels)))
        self.db.mark_processed(message.gmail_message_id, classification.category)

        if details and details.is_interview:
            self.db.upsert_interview(
                email=message,
                details=details,
                status=interview_status or "needs_review",
                calendar_event_id=calendar_event_id,
                cloud_backup_path=backup_path,
            )
        LOGGER.info(
            "Processed message",
            extra={
                "gmail_message_id": message.gmail_message_id,
                "thread_id": message.thread_id,
                "category": classification.category,
                "status": interview_status or "processed",
                "event_id": calendar_event_id,
            },
        )

    def _resolve_event_id(self, message, details) -> str | None:
        by_msg_id = self.calendar.find_by_message_id(message.gmail_message_id)
        if by_msg_id:
            return by_msg_id["id"]
        existing_thread = self.db.get_interview_by_thread_id(message.thread_id)
        if existing_thread and existing_thread["calendar_event_id"]:
            return existing_thread["calendar_event_id"]
        duplicate = self.calendar.find_potential_duplicate(details)
        if duplicate:
            return duplicate["id"]
        return None

