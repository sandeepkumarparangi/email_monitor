from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

from googleapiclient.discovery import build

from app.config import AppConfig, google_scopes
from app.google_auth import get_credentials
from app.models import AttachmentMeta, DownloadedAttachment, EmailMessageData
from app.retry_utils import with_retry


class GmailService:
    def __init__(self, config: AppConfig, client=None) -> None:
        self.config = config
        self.client = client or self._build_client()
        self._label_name_to_id: Dict[str, str] = {}

    def _build_client(self):
        creds = get_credentials(
            credentials_file=self.config.google_credentials_file,
            token_file=self.config.google_token_file,
            scopes=google_scopes(self.config),
            oauth_port=self.config.google_oauth_port,
        )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    @with_retry(retries=3)
    def ensure_labels(self, labels: List[str]) -> None:
        existing = self.client.users().labels().list(userId="me").execute().get("labels", [])
        self._label_name_to_id = {label["name"]: label["id"] for label in existing}
        for name in labels:
            if name in self._label_name_to_id:
                continue
            created = self.client.users().labels().create(
                userId="me",
                body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
            ).execute()
            self._label_name_to_id[name] = created["id"]

    @with_retry(retries=3)
    def list_message_ids(self) -> List[str]:
        # Exclude already-processed messages using the marker label so Railway DB resets don't reprocess
        query = self.config.gmail_query
        if self.config.processed_marker_label in self._label_name_to_id:
            query = f"{query} -label:{self.config.processed_marker_label.replace(' ', '-')}"
        result = self.client.users().messages().list(
            userId="me",
            q=query,
            maxResults=self.config.gmail_max_results,
        ).execute()
        return [item["id"] for item in result.get("messages", [])]

    @with_retry(retries=3)
    def get_message(self, message_id: str) -> EmailMessageData:
        payload = self.client.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in payload.get("payload", {}).get("headers", [])}
        sender = headers.get("from", "")
        subject = headers.get("subject", "")
        date_header = headers.get("date")
        received_at = parsedate_to_datetime(date_header).astimezone(timezone.utc) if date_header else datetime.now(tz=timezone.utc)
        body = self._extract_body(payload.get("payload", {}))
        attachments = self._extract_attachment_meta(payload.get("payload", {}))
        return EmailMessageData(
            gmail_message_id=payload["id"],
            thread_id=payload["threadId"],
            sender=sender,
            subject=subject,
            body=body,
            received_at=received_at,
            internal_date_ms=int(payload.get("internalDate", "0")),
            attachments=attachments,
        )

    def _extract_body(self, payload: dict) -> str:
        # Prefer plain text
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return self._decode(payload["body"]["data"])
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return self._decode(part["body"]["data"])
        # Fall back to HTML stripped of tags
        if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
            return self._strip_html(self._decode(payload["body"]["data"]))
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                return self._strip_html(self._decode(part["body"]["data"]))
        for part in payload.get("parts", []):
            nested = self._extract_body(part)
            if nested:
                return nested
        return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        import re as _re
        text = _re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=_re.S | _re.I)
        text = _re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=_re.S | _re.I)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"&nbsp;", " ", text)
        text = _re.sub(r"&amp;", "&", text)
        text = _re.sub(r"&lt;", "<", text)
        text = _re.sub(r"&gt;", ">", text)
        text = _re.sub(r"[ \t]{2,}", " ", text)
        text = _re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_attachment_meta(self, payload: dict) -> List[AttachmentMeta]:
        results: List[AttachmentMeta] = []
        for part in payload.get("parts", []):
            filename = part.get("filename", "")
            body = part.get("body", {})
            if filename and body.get("attachmentId"):
                results.append(
                    AttachmentMeta(
                        filename=filename,
                        mime_type=part.get("mimeType", "application/octet-stream"),
                        attachment_id=body["attachmentId"],
                        size=int(body.get("size", 0)),
                    )
                )
            results.extend(self._extract_attachment_meta(part))
        return results

    @staticmethod
    def _decode(encoded: str) -> str:
        return base64.urlsafe_b64decode(encoded.encode("utf-8")).decode("utf-8", errors="replace")

    @with_retry(retries=3)
    def apply_labels(self, message_id: str, label_names: List[str]) -> None:
        label_ids = [self._label_name_to_id[name] for name in label_names if name in self._label_name_to_id]
        if not label_ids:
            return
        self.client.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": label_ids, "removeLabelIds": []},
        ).execute()

    @with_retry(retries=3)
    def download_attachments(self, message: EmailMessageData) -> List[DownloadedAttachment]:
        results: List[DownloadedAttachment] = []
        for attachment in message.attachments:
            response = self.client.users().messages().attachments().get(
                userId="me",
                messageId=message.gmail_message_id,
                id=attachment.attachment_id,
            ).execute()
            raw = response.get("data")
            if not raw:
                continue
            content = base64.urlsafe_b64decode(raw.encode("utf-8"))
            results.append(
                DownloadedAttachment(
                    filename=attachment.filename,
                    mime_type=attachment.mime_type,
                    content=content,
                )
            )
        return results
