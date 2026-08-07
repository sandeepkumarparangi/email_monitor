from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from app.calendar_service import CalendarService
from app.classifier import EmailClassifier
from app.cloud_storage import CloudStorageProvider
from app.config import AppConfig
from app.database import AgentDatabase, normalize_subject
from app.gmail_service import GmailService
from app.interview_extractor import InterviewExtractor
from app.models import EmailMessageData, InterviewDetails


LOGGER = logging.getLogger(__name__)
GENERIC_SUBJECT_KEYS = {"interview invitation", "interview", "updated interview", "calendar invite"}


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
            attachments = self.gmail.download_attachments(message)
            details = self.extractor.extract(message, attachments)
            if details.is_interview:
                existing_record = self._find_related_interview_record(message, details)
                if existing_record:
                    details = self.extractor.merge_with_existing(details, self._row_to_details(existing_record))
                if details.needs_review:
                    interview_status = "needs_review"
                    labels.append(EmailClassifier.LABEL_MAP["Interview - Needs Review"])
                else:
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
        if details.calendar_uid:
            by_calendar_uid = self.calendar.find_by_calendar_uid(details.calendar_uid)
            if by_calendar_uid:
                return by_calendar_uid["id"]
        by_msg_id = self.calendar.find_by_message_id(message.gmail_message_id)
        if by_msg_id:
            return by_msg_id["id"]
        existing_thread = self.db.get_interview_by_thread_id(message.thread_id)
        if existing_thread and existing_thread["calendar_event_id"]:
            return existing_thread["calendar_event_id"]
        if details.meeting_link:
            existing_link = self.db.get_interview_by_meeting_link(details.meeting_link)
            if existing_link and existing_link["calendar_event_id"]:
                return existing_link["calendar_event_id"]
        subject_key = normalize_subject(message.subject)
        if self._usable_subject_key(subject_key):
            existing_subject = self.db.get_interview_by_subject_key(subject_key)
            if existing_subject and existing_subject["calendar_event_id"]:
                return existing_subject["calendar_event_id"]
        duplicate = self.calendar.find_potential_duplicate(details)
        if duplicate:
            return duplicate["id"]
        return None

    def _find_related_interview_record(self, message: EmailMessageData, details: InterviewDetails):
        if details.calendar_uid:
            by_uid = self.db.get_interview_by_calendar_uid(details.calendar_uid)
            if by_uid:
                return by_uid
        by_thread = self.db.get_interview_by_thread_id(message.thread_id)
        if by_thread:
            return by_thread
        if details.meeting_link:
            by_link = self.db.get_interview_by_meeting_link(details.meeting_link)
            if by_link:
                return by_link
        subject_key = normalize_subject(message.subject)
        if self._usable_subject_key(subject_key):
            by_subject = self.db.get_interview_by_subject_key(subject_key)
            if by_subject and self._subject_match_is_safe(by_subject, details):
                return by_subject
        return None

    @staticmethod
    def _usable_subject_key(subject_key: str) -> bool:
        return bool(subject_key) and subject_key not in GENERIC_SUBJECT_KEYS and len(subject_key) >= 15

    @staticmethod
    def _subject_match_is_safe(existing_record, details: InterviewDetails) -> bool:
        if details.company and existing_record["company"] and details.company != existing_record["company"]:
            return False
        if details.recruiter_email and existing_record["recruiter_email"] and details.recruiter_email != existing_record["recruiter_email"]:
            return False
        return True

    @staticmethod
    def _row_to_details(row) -> InterviewDetails:
        return InterviewDetails(
            is_interview=True,
            needs_review=row["status"] == "needs_review",
            missing_fields=[field for field in (row["missing_fields"] or "").split(",") if field],
            action=row["action"] or "schedule",
            company=row["company"],
            job_title=row["job_title"],
            recruiter=row["recruiter"],
            recruiter_email=row["recruiter_email"],
            interview_start=datetime.fromisoformat(row["interview_start"]) if row["interview_start"] else None,
            interview_end=datetime.fromisoformat(row["interview_end"]) if row["interview_end"] else None,
            original_timezone=row["timezone"],
            interview_type=row["interview_type"],
            meeting_link=row["meeting_link"],
            review_reason=row["review_reason"],
            calendar_uid=row["calendar_uid"],
            source_kind=row["source_kind"],
        )
