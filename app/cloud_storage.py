from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from datetime import timezone
from pathlib import Path
from typing import List, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import AppConfig, google_scopes
from app.google_auth import get_credentials
from app.models import DownloadedAttachment, EmailMessageData, InterviewDetails
from app.retry_utils import with_retry


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.\-_ ]", "_", filename).strip()
    return cleaned[:200] or "unnamed_file"


class CloudStorageProvider(ABC):
    @abstractmethod
    def backup_interview(
        self,
        details: InterviewDetails,
        email: EmailMessageData,
        attachments: List[DownloadedAttachment],
    ) -> str:
        raise NotImplementedError


class LocalCloudStorageProvider(CloudStorageProvider):
    def __init__(self, root_dir: str) -> None:
        self.root = Path(root_dir)

    def backup_interview(
        self,
        details: InterviewDetails,
        email: EmailMessageData,
        attachments: List[DownloadedAttachment],
    ) -> str:
        company = sanitize_filename(details.company or "Unknown Company")
        role = sanitize_filename(details.job_title or "Unknown Role")
        base = self.root / "Job Search" / company / role
        details_dir = base / "Interview Details"
        attachments_dir = base / "Attachments"
        details_dir.mkdir(parents=True, exist_ok=True)
        attachments_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "company": details.company,
            "position": details.job_title,
            "interview_start": details.interview_start.isoformat() if details.interview_start else None,
            "interview_end": details.interview_end.isoformat() if details.interview_end else None,
            "timezone": details.original_timezone,
            "recruiter": details.recruiter,
            "recruiter_email": details.recruiter_email,
            "meeting_link": details.meeting_link,
            "interview_instructions": details.instructions,
            "action": details.action,
            "review_reason": details.review_reason,
            "calendar_uid": details.calendar_uid,
            "source_kind": details.source_kind,
            "email_subject": email.subject,
            "gmail_message_id": email.gmail_message_id,
            "status": "needs_review" if details.needs_review else "scheduled",
            "processed_at": email.received_at.astimezone(timezone.utc).isoformat(),
        }
        record_file = details_dir / f"{email.gmail_message_id}.json"
        record_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        for attachment in attachments:
            filename = sanitize_filename(attachment.filename)
            (attachments_dir / filename).write_bytes(attachment.content)
        return str(base)


class GoogleDriveStorageProvider(CloudStorageProvider):
    def __init__(self, config: AppConfig, client=None) -> None:
        self.config = config
        self.client = client or self._build_client()
        self.root_folder_id = self._ensure_folder(self.config.drive_root_folder, None)

    def _build_client(self):
        creds = get_credentials(
            credentials_file=self.config.google_credentials_file,
            token_file=self.config.google_token_file,
            scopes=google_scopes(self.config),
            oauth_port=self.config.google_oauth_port,
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    @with_retry(retries=3)
    def _ensure_folder(self, folder_name: str, parent_id: Optional[str]) -> str:
        escaped_name = folder_name.replace("'", "\\'")
        q_parts = [f"name = '{escaped_name}'", "mimeType = 'application/vnd.google-apps.folder'", "trashed = false"]
        if parent_id:
            q_parts.append(f"'{parent_id}' in parents")
        query = " and ".join(q_parts)
        existing = self.client.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=1).execute()
        files = existing.get("files", [])
        if files:
            return files[0]["id"]
        metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = self.client.files().create(body=metadata, fields="id").execute()
        return folder["id"]

    @with_retry(retries=3)
    def _upload_file(self, name: str, parent_id: str, raw: bytes, mime_type: str) -> None:
        import io

        media = MediaIoBaseUpload(io.BytesIO(raw), mimetype=mime_type, resumable=False)
        body = {"name": name, "parents": [parent_id]}
        self.client.files().create(body=body, media_body=media, fields="id").execute()

    def backup_interview(
        self,
        details: InterviewDetails,
        email: EmailMessageData,
        attachments: List[DownloadedAttachment],
    ) -> str:
        company = sanitize_filename(details.company or "Unknown Company")
        role = sanitize_filename(details.job_title or "Unknown Role")
        company_folder = self._ensure_folder(company, self.root_folder_id)
        role_folder = self._ensure_folder(role, company_folder)
        details_folder = self._ensure_folder("Interview Details", role_folder)
        attachments_folder = self._ensure_folder("Attachments", role_folder)

        record = {
            "company": details.company,
            "position": details.job_title,
            "interview_start": details.interview_start.isoformat() if details.interview_start else None,
            "interview_end": details.interview_end.isoformat() if details.interview_end else None,
            "timezone": details.original_timezone,
            "recruiter": details.recruiter,
            "recruiter_email": details.recruiter_email,
            "meeting_link": details.meeting_link,
            "interview_instructions": details.instructions,
            "action": details.action,
            "review_reason": details.review_reason,
            "calendar_uid": details.calendar_uid,
            "source_kind": details.source_kind,
            "email_subject": email.subject,
            "gmail_message_id": email.gmail_message_id,
            "status": "needs_review" if details.needs_review else "scheduled",
            "processed_at": email.received_at.astimezone(timezone.utc).isoformat(),
        }
        self._upload_file(
            f"{email.gmail_message_id}.json",
            details_folder,
            json.dumps(record, indent=2).encode("utf-8"),
            "application/json",
        )
        for attachment in attachments:
            self._upload_file(
                sanitize_filename(attachment.filename),
                attachments_folder,
                attachment.content,
                attachment.mime_type,
            )
        return f"{self.config.drive_root_folder}/{company}/{role}"


def create_cloud_storage_provider(config: AppConfig) -> CloudStorageProvider:
    if config.storage_provider == "drive":
        return GoogleDriveStorageProvider(config)
    if config.storage_provider == "local":
        return LocalCloudStorageProvider(config.local_backup_dir)
    raise ValueError(f"Unsupported STORAGE_PROVIDER '{config.storage_provider}'. Use 'drive' or 'local'.")
