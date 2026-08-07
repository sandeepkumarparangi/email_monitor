from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from app.models import EmailMessageData, InterviewDetails


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


REPLY_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fw|fwd)\s*:\s*)+", re.I)
NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize_subject(subject: str) -> str:
    lowered = REPLY_PREFIX_RE.sub("", subject or "").strip().lower()
    normalized = NON_WORD_RE.sub(" ", lowered)
    return " ".join(normalized.split())


class AgentDatabase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

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
                    email_subject TEXT,
                    subject_key TEXT,
                    company TEXT,
                    job_title TEXT,
                    recruiter TEXT,
                    recruiter_email TEXT,
                    interview_start TEXT,
                    interview_end TEXT,
                    timezone TEXT,
                    interview_type TEXT,
                    meeting_link TEXT,
                    calendar_uid TEXT,
                    calendar_event_id TEXT,
                    cloud_backup_path TEXT,
                    status TEXT NOT NULL,
                    action TEXT NOT NULL DEFAULT 'schedule',
                    missing_fields TEXT,
                    review_reason TEXT,
                    source_kind TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "interviews", "email_subject", "TEXT")
            self._ensure_column(conn, "interviews", "subject_key", "TEXT")
            self._ensure_column(conn, "interviews", "calendar_uid", "TEXT")
            self._ensure_column(conn, "interviews", "action", "TEXT NOT NULL DEFAULT 'schedule'")
            self._ensure_column(conn, "interviews", "review_reason", "TEXT")
            self._ensure_column(conn, "interviews", "source_kind", "TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interviews_thread_id ON interviews(thread_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interviews_calendar_uid ON interviews(calendar_uid);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interviews_subject_key ON interviews(subject_key);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interviews_meeting_link ON interviews(meeting_link);"
            )

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name});").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition};")

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
            cursor = conn.execute(
                """
                UPDATE emails
                SET processing_status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = ?
                WHERE gmail_message_id = ?;
                """,
                (error[:2000], gmail_message_id),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    """
                    INSERT INTO emails (
                        gmail_message_id, thread_id, sender, subject, received_at, processing_status, retry_count, last_error
                    ) VALUES (?, '', '', '', ?, 'failed', 1, ?)
                    ON CONFLICT(gmail_message_id) DO UPDATE SET
                        processing_status='failed',
                        retry_count=emails.retry_count + 1,
                        last_error=excluded.last_error;
                    """,
                    (gmail_message_id, utc_now_iso(), error[:2000]),
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

    def get_interview_by_calendar_uid(self, calendar_uid: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                """
                SELECT * FROM interviews
                WHERE calendar_uid = ?
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (calendar_uid,),
            ).fetchone()

    def get_interview_by_meeting_link(self, meeting_link: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                """
                SELECT * FROM interviews
                WHERE meeting_link = ?
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (meeting_link,),
            ).fetchone()

    def get_interview_by_subject_key(self, subject_key: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                """
                SELECT * FROM interviews
                WHERE subject_key = ?
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (subject_key,),
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
                    gmail_message_id, thread_id, email_subject, subject_key, company, job_title, recruiter, recruiter_email,
                    interview_start, interview_end, timezone, interview_type, meeting_link, calendar_uid,
                    calendar_event_id, cloud_backup_path, status, action, missing_fields, review_reason, source_kind, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(gmail_message_id) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    email_subject=excluded.email_subject,
                    subject_key=excluded.subject_key,
                    company=excluded.company,
                    job_title=excluded.job_title,
                    recruiter=excluded.recruiter,
                    recruiter_email=excluded.recruiter_email,
                    interview_start=excluded.interview_start,
                    interview_end=excluded.interview_end,
                    timezone=excluded.timezone,
                    interview_type=excluded.interview_type,
                    meeting_link=excluded.meeting_link,
                    calendar_uid=excluded.calendar_uid,
                    calendar_event_id=excluded.calendar_event_id,
                    cloud_backup_path=excluded.cloud_backup_path,
                    status=excluded.status,
                    action=excluded.action,
                    missing_fields=excluded.missing_fields,
                    review_reason=excluded.review_reason,
                    source_kind=excluded.source_kind,
                    updated_at=excluded.updated_at;
                """,
                (
                    email.gmail_message_id,
                    email.thread_id,
                    email.subject,
                    normalize_subject(email.subject),
                    details.company,
                    details.job_title,
                    details.recruiter,
                    details.recruiter_email,
                    details.interview_start.isoformat() if details.interview_start else None,
                    details.interview_end.isoformat() if details.interview_end else None,
                    details.original_timezone,
                    details.interview_type,
                    details.meeting_link,
                    details.calendar_uid,
                    calendar_event_id,
                    cloud_backup_path,
                    status,
                    details.action,
                    ",".join(details.missing_fields),
                    details.review_reason,
                    details.source_kind,
                    utc_now_iso(),
                ),
            )

    def get_dashboard_snapshot(self, limit: int) -> dict[str, Any]:
        with self._conn() as conn:
            counts_row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM interviews WHERE status = 'needs_review') AS needs_review_count,
                    (SELECT COUNT(*) FROM emails WHERE processing_status = 'failed') AS failed_count,
                    (SELECT COUNT(*) FROM emails WHERE processed_at IS NOT NULL) AS processed_count;
                """
            ).fetchone()
            needs_review_rows = conn.execute(
                """
                SELECT
                    i.gmail_message_id,
                    i.thread_id,
                    COALESCE(i.email_subject, e.subject) AS subject,
                    e.sender,
                    i.company,
                    i.job_title,
                    i.interview_start,
                    i.interview_end,
                    i.meeting_link,
                    i.action,
                    i.review_reason,
                    i.missing_fields,
                    i.updated_at
                FROM interviews i
                LEFT JOIN emails e ON e.gmail_message_id = i.gmail_message_id
                WHERE i.status = 'needs_review'
                ORDER BY i.updated_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            failed_rows = conn.execute(
                """
                SELECT
                    gmail_message_id,
                    thread_id,
                    sender,
                    subject,
                    received_at,
                    retry_count,
                    last_error,
                    processing_status
                FROM emails
                WHERE processing_status = 'failed'
                ORDER BY COALESCE(processed_at, received_at) DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        return {
            "counts": dict(counts_row) if counts_row is not None else {},
            "needs_review": [dict(row) for row in needs_review_rows],
            "failures": [dict(row) for row in failed_rows],
        }
