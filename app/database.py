from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.models import ClassificationResult, EmailMessageData, InterviewDetails


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class AgentDatabase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        # Auto-create parent directory (needed for Railway volumes like /data)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS emails (
                    gmail_message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    category TEXT,
                    processed_at TEXT,
                    processing_status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interviews (
                    gmail_message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    company TEXT,
                    job_title TEXT,
                    recruiter TEXT,
                    recruiter_email TEXT,
                    interview_start TEXT,
                    interview_end TEXT,
                    timezone TEXT,
                    interview_type TEXT,
                    meeting_link TEXT,
                    calendar_event_id TEXT,
                    cloud_backup_path TEXT,
                    status TEXT NOT NULL,
                    missing_fields TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interviews_thread_id ON interviews(thread_id);"
            )

    def is_processed(self, gmail_message_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT processed_at FROM emails WHERE gmail_message_id = ?",
                (gmail_message_id,),
            ).fetchone()
            return row is not None and row["processed_at"] is not None

    def upsert_email_received(self, email: EmailMessageData) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO emails (
                    gmail_message_id, thread_id, sender, subject, received_at, processing_status
                ) VALUES (?, ?, ?, ?, ?, 'pending')
                ON CONFLICT(gmail_message_id) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    sender=excluded.sender,
                    subject=excluded.subject,
                    received_at=excluded.received_at;
                """,
                (
                    email.gmail_message_id,
                    email.thread_id,
                    email.sender,
                    email.subject,
                    email.received_at.isoformat(),
                ),
            )

    def mark_processed(self, gmail_message_id: str, category: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE emails
                SET processed_at = ?, category = ?, processing_status = 'done', last_error = NULL
                WHERE gmail_message_id = ?;
                """,
                (utc_now_iso(), category, gmail_message_id),
            )

    def mark_failed(self, gmail_message_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE emails
                SET processing_status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = ?
                WHERE gmail_message_id = ?;
                """,
                (error[:2000], gmail_message_id),
            )

    def get_interview_by_thread_id(self, thread_id: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                """
                SELECT * FROM interviews
                WHERE thread_id = ?
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (thread_id,),
            ).fetchone()

    def upsert_interview(
        self,
        email: EmailMessageData,
        details: InterviewDetails,
        status: str,
        calendar_event_id: Optional[str],
        cloud_backup_path: Optional[str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO interviews (
                    gmail_message_id, thread_id, company, job_title, recruiter, recruiter_email,
                    interview_start, interview_end, timezone, interview_type, meeting_link,
                    calendar_event_id, cloud_backup_path, status, missing_fields, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(gmail_message_id) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    company=excluded.company,
                    job_title=excluded.job_title,
                    recruiter=excluded.recruiter,
                    recruiter_email=excluded.recruiter_email,
                    interview_start=excluded.interview_start,
                    interview_end=excluded.interview_end,
                    timezone=excluded.timezone,
                    interview_type=excluded.interview_type,
                    meeting_link=excluded.meeting_link,
                    calendar_event_id=excluded.calendar_event_id,
                    cloud_backup_path=excluded.cloud_backup_path,
                    status=excluded.status,
                    missing_fields=excluded.missing_fields,
                    updated_at=excluded.updated_at;
                """,
                (
                    email.gmail_message_id,
                    email.thread_id,
                    details.company,
                    details.job_title,
                    details.recruiter,
                    details.recruiter_email,
                    details.interview_start.isoformat() if details.interview_start else None,
                    details.interview_end.isoformat() if details.interview_end else None,
                    details.original_timezone,
                    details.interview_type,
                    details.meeting_link,
                    calendar_event_id,
                    cloud_backup_path,
                    status,
                    ",".join(details.missing_fields),
                    utc_now_iso(),
                ),
            )

