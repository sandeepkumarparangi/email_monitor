from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.dashboard import render_dashboard_html
from app.database import AgentDatabase
from app.models import EmailMessageData, InterviewDetails


def test_dashboard_renders_needs_review_and_failures(app_config):
    db = AgentDatabase(app_config.database_path)
    db.initialize()

    email = EmailMessageData(
        gmail_message_id="m-review",
        thread_id="t-review",
        sender="Recruiter <recruiter@acme.com>",
        subject="Interview availability request",
        body="Please share your availability for an interview next week.",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    db.upsert_email_received(email)
    db.upsert_interview(
        email=email,
        details=InterviewDetails(
            is_interview=True,
            needs_review=True,
            missing_fields=["interview_start"],
            action="availability",
            company="Acme",
            job_title="Engineer",
            review_reason="Candidate availability requested but no confirmed interview time was provided.",
        ),
        status="needs_review",
        calendar_event_id=None,
        cloud_backup_path=None,
    )
    db.mark_failed("m-failed", "calendar update failed")

    snapshot = db.get_dashboard_snapshot(limit=10)
    html = render_dashboard_html(snapshot)

    assert snapshot["counts"]["needs_review_count"] == 1
    assert snapshot["counts"]["failed_count"] == 1
    assert "Interview availability request" in html
    assert "calendar update failed" in html
