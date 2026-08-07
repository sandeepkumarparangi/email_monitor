from __future__ import annotations

from datetime import timedelta
from typing import Optional

from googleapiclient.discovery import build

from app.config import AppConfig, google_scopes
from app.google_auth import get_credentials
from app.models import EmailMessageData, InterviewDetails
from app.retry_utils import with_retry


class CalendarService:
    def __init__(self, config: AppConfig, client=None) -> None:
        self.config = config
        self.client = client or self._build_client()

    def _build_client(self):
        creds = get_credentials(
            credentials_file=self.config.google_credentials_file,
            token_file=self.config.google_token_file,
            scopes=google_scopes(self.config),
            oauth_port=self.config.google_oauth_port,
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @with_retry(retries=3)
    def find_by_message_id(self, gmail_message_id: str) -> Optional[dict]:
        events = self.client.events().list(
            calendarId=self.config.calendar_id,
            privateExtendedProperty=f"gmail_message_id={gmail_message_id}",
            maxResults=1,
            singleEvents=True,
        ).execute().get("items", [])
        return events[0] if events else None

    @with_retry(retries=3)
    def find_potential_duplicate(self, details: InterviewDetails) -> Optional[dict]:
        if not details.interview_start:
            return None
        time_min = (details.interview_start - timedelta(days=1)).isoformat()
        time_max = (details.interview_start + timedelta(days=1)).isoformat()
        events = self.client.events().list(
            calendarId=self.config.calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute().get("items", [])
        for event in events:
            summary = event.get("summary", "").lower()
            description = event.get("description", "").lower()
            if details.company and details.company.lower() in summary:
                return event
            if details.meeting_link and details.meeting_link.lower() in description:
                return event
        return None

    def _build_title(self, details: InterviewDetails) -> str:
        company = details.company or "Unknown Company"
        job = details.job_title or "Unknown Role"
        return f"Interview - {company} - {job}"

    def _build_description(self, details: InterviewDetails, email: EmailMessageData) -> str:
        lines = [
            f"Company: {details.company or 'Unknown'}",
            f"Job Title: {details.job_title or 'Unknown'}",
            f"Recruiter/Interviewer: {details.recruiter or 'Unknown'}",
            f"Recruiter Email: {details.recruiter_email or 'Unknown'}",
            f"Interview Type: {details.interview_type or 'Unknown'}",
            f"Original Timezone: {details.original_timezone or 'Unknown'}",
            f"Meeting URL: {details.meeting_link or 'N/A'}",
            f"Phone: {details.phone_number or 'N/A'}",
            f"Location: {details.location or 'N/A'}",
            f"Instructions: {details.instructions or 'N/A'}",
            f"Gmail Message ID: {email.gmail_message_id}",
            f"Gmail Thread ID: {email.thread_id}",
            f"Email Subject: {email.subject}",
        ]
        return "\n".join(lines)

    def _build_event_body(self, details: InterviewDetails, email: EmailMessageData) -> dict:
        if not details.interview_start or not details.interview_end:
            raise ValueError("Interview start/end must exist before creating calendar event")
        return {
            "summary": self._build_title(details),
            "description": self._build_description(details, email),
            "start": {"dateTime": details.interview_start.isoformat()},
            "end": {"dateTime": details.interview_end.isoformat()},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 60},
                ],
            },
            "extendedProperties": {
                "private": {
                    "gmail_message_id": email.gmail_message_id,
                    "gmail_thread_id": email.thread_id,
                }
            },
        }

    @with_retry(retries=3)
    def create_event(self, details: InterviewDetails, email: EmailMessageData) -> str:
        body = self._build_event_body(details, email)
        event = self.client.events().insert(calendarId=self.config.calendar_id, body=body).execute()
        return event["id"]

    @with_retry(retries=3)
    def update_event(self, event_id: str, details: InterviewDetails, email: EmailMessageData) -> str:
        body = self._build_event_body(details, email)
        event = self.client.events().update(
            calendarId=self.config.calendar_id,
            eventId=event_id,
            body=body,
        ).execute()
        return event["id"]
