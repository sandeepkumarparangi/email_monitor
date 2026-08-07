from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class AttachmentMeta:
    filename: str
    mime_type: str
    attachment_id: str
    size: int = 0


@dataclass
class DownloadedAttachment:
    filename: str
    mime_type: str
    content: bytes


@dataclass
class EmailMessageData:
    gmail_message_id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    internal_date_ms: int
    attachments: List[AttachmentMeta] = field(default_factory=list)


@dataclass
class ClassificationResult:
    category: str
    reason: str
    label: str


@dataclass
class InterviewDetails:
    is_interview: bool
    needs_review: bool
    missing_fields: List[str]
    company: Optional[str] = None
    job_title: Optional[str] = None
    recruiter: Optional[str] = None
    recruiter_email: Optional[str] = None
    interview_start: Optional[datetime] = None
    interview_end: Optional[datetime] = None
    original_timezone: Optional[str] = None
    interview_type: Optional[str] = None
    meeting_link: Optional[str] = None
    phone_number: Optional[str] = None
    location: Optional[str] = None
    instructions: Optional[str] = None
    source_snippet: Optional[str] = None

