from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.models import DownloadedAttachment, EmailMessageData, InterviewDetails


class FakeGmailService:
    def __init__(self, emails: Dict[str, EmailMessageData], attachments: Dict[str, List[DownloadedAttachment]] | None = None):
        self.emails = emails
        self.applied_labels: Dict[str, List[str]] = {}
        self.attachments = attachments or {}
        self.ensured_labels: List[str] = []

    def ensure_labels(self, labels: List[str]) -> None:
        self.ensured_labels = labels

    def list_message_ids(self) -> List[str]:
        return list(self.emails.keys())

    def get_message(self, message_id: str) -> EmailMessageData:
        return self.emails[message_id]

    def apply_labels(self, message_id: str, label_names: List[str]) -> None:
        self.applied_labels[message_id] = label_names

    def download_attachments(self, message: EmailMessageData) -> List[DownloadedAttachment]:
        return self.attachments.get(message.gmail_message_id, [])


class FakeCalendarService:
    def __init__(self):
        self.events: Dict[str, dict] = {}
        self.by_message_id: Dict[str, str] = {}
        self.created_count = 0
        self.updated_count = 0

    def find_by_message_id(self, gmail_message_id: str) -> Optional[dict]:
        event_id = self.by_message_id.get(gmail_message_id)
        return self.events.get(event_id) if event_id else None

    def find_potential_duplicate(self, details: InterviewDetails) -> Optional[dict]:
        for event in self.events.values():
            if details.meeting_link and event.get("meeting_link") == details.meeting_link:
                return event
        return None

    def create_event(self, details: InterviewDetails, email: EmailMessageData) -> str:
        self.created_count += 1
        event_id = f"evt-{self.created_count}"
        self.events[event_id] = {"id": event_id, "meeting_link": details.meeting_link}
        self.by_message_id[email.gmail_message_id] = event_id
        return event_id

    def update_event(self, event_id: str, details: InterviewDetails, email: EmailMessageData) -> str:
        self.updated_count += 1
        self.events[event_id] = {"id": event_id, "meeting_link": details.meeting_link}
        self.by_message_id[email.gmail_message_id] = event_id
        return event_id

