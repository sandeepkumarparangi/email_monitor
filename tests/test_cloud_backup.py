from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.cloud_storage import LocalCloudStorageProvider, sanitize_filename
from app.models import DownloadedAttachment, EmailMessageData, InterviewDetails


def test_sanitize_filename():
    assert sanitize_filename("offer<>doc?.pdf") == "offer__doc_.pdf"


def test_local_backup_writes_record_and_attachments(tmp_path):
    provider = LocalCloudStorageProvider(str(tmp_path))
    details = InterviewDetails(
        is_interview=True,
        needs_review=False,
        missing_fields=[],
        company="Acme",
        job_title="Software Engineer",
        recruiter="Alice",
        recruiter_email="alice@acme.com",
        interview_start=datetime(2026, 8, 12, 11, 0, tzinfo=ZoneInfo("America/Chicago")),
        interview_end=datetime(2026, 8, 12, 12, 0, tzinfo=ZoneInfo("America/Chicago")),
        original_timezone="America/Chicago",
    )
    email = EmailMessageData(
        gmail_message_id="m-1",
        thread_id="t-1",
        sender="Alice <alice@acme.com>",
        subject="Interview",
        body="",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    path = provider.backup_interview(
        details,
        email,
        [DownloadedAttachment(filename="JD?.pdf", mime_type="application/pdf", content=b"pdf")],
    )
    assert "Acme" in path
    assert (tmp_path / "Job Search" / "Acme" / "Software Engineer" / "Interview Details" / "m-1.json").exists()
    assert (tmp_path / "Job Search" / "Acme" / "Software Engineer" / "Attachments" / "JD_.pdf").exists()

