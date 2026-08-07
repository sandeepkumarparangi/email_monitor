from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.classifier import EmailClassifier
from app.models import EmailMessageData


def test_classifier_detects_interview():
    classifier = EmailClassifier()
    email = EmailMessageData(
        gmail_message_id="m1",
        thread_id="t1",
        sender="Recruiter <recruiter@company.com>",
        subject="Interview invitation for Software Engineer role",
        body="Can you interview on Tuesday at 2 PM CST?",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    result = classifier.classify(email)
    assert result.category == "Interview / Interview Invitation"
    assert result.label == "AI-Interview"


def test_classifier_detects_assessment():
    classifier = EmailClassifier()
    email = EmailMessageData(
        gmail_message_id="m2",
        thread_id="t2",
        sender="HR <hr@company.com>",
        subject="HackerRank Assessment",
        body="Please complete your coding test by Friday.",
        received_at=datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago")),
        internal_date_ms=0,
    )
    result = classifier.classify(email)
    assert result.category == "Assessment / HackerRank / Coding Test"
