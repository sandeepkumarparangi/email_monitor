from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.models import ClassificationResult, EmailMessageData


class EmailClassifier:
    CATEGORY_RULES: List[Tuple[str, List[str]]] = [
        ("Interview / Interview Invitation", [
            "interview", "panel", "onsite", "on-site", "schedule.*interview",
            "technical screen", "phone screen", "video call", "hiring manager",
            "virtual interview", "meet with", "meet our team",
        ]),
        ("Assessment / HackerRank / Coding Test", [
            "hackerrank", "codility", "codesignal", "coding assessment",
            "coding test", "assessment", "take-home", "technical challenge",
            "test link", "online assessment",
        ]),
        ("Offer", [
            "offer letter", "job offer", "we are excited to offer",
            "extend an offer", "compensation package", "start date",
            "sign.*offer", "offer.*accept",
        ]),
        ("Rejection", [
            "unfortunately", "not moving forward", "regret to inform",
            "not selected", "decided to move forward with other",
            "will not be moving", "not a match", "position has been filled",
            "after careful consideration", "not be proceeding",
        ]),
        ("Job Application Update", [
            "application status", "your application", "thank you for applying",
            "thanks for applying", "we received your application",
            "application.*received", "next steps", "application.*review",
            "reviewing your application", "moving forward with your application",
            "status update",
        ]),
        ("Recruiter / Job Opportunity", [
            "recruiter", "new opportunity", "exciting opportunity",
            "job opportunity", "open role", "open position",
            "i came across your profile", "i found your profile",
            "reach out.*role", "reach out.*opportunity",
            "software engineer.*opportunity", "engineering role",
            "we.*hiring", "we are looking for",
        ]),
        ("Work / Professional", [
            "project update", "pull request", "code review",
            "meeting agenda", "sprint", "standup", "jira",
            "confluence", "deployment", "release notes",
        ]),
        ("Finance", [
            "invoice", "payment due", "bank statement",
            "your receipt", "transaction", "payroll", "direct deposit",
        ]),
        ("Promotions", [
            "unsubscribe", "% off", "sale ends", "limited time",
            "promo code", "discount", "special offer", "deal of the day",
        ]),
        ("Spam / Unimportant", [
            "lottery", "you have won", "claim prize", "urgent transfer",
            "wire transfer", "nigerian", "inheritance",
        ]),
        ("Personal", [
            "family", "birthday", "party invite", "dinner plans", "vacation",
        ]),
    ]

    LABEL_MAP: Dict[str, str] = {
        "Interview / Interview Invitation": "AI-Interview",
        "Interview - Needs Review": "AI-Interview-Needs-Review",
        "Recruiter / Job Opportunity": "AI-Recruiter",
        "Job Application Update": "AI-Application-Update",
        "Assessment / HackerRank / Coding Test": "AI-Assessment",
        "Rejection": "AI-Rejection",
        "Offer": "AI-Offer",
        "Work / Professional": "AI-Work",
        "Finance": "AI-Finance",
        "Personal": "AI-Personal",
        "Promotions": "AI-Promotions",
        "Spam / Unimportant": "AI-Spam",
        "Other": "AI-Other",
    }

    def classify(self, email: EmailMessageData) -> ClassificationResult:
        normalized = f"{email.subject}\n{email.body}".lower()
        for category, patterns in self.CATEGORY_RULES:
            for pattern in patterns:
                # Patterns containing regex special chars (.*) are used as-is; others use word boundary
                if any(c in pattern for c in [".*", "^", "("]):
                    if re.search(pattern, normalized):
                        return ClassificationResult(
                            category=category,
                            reason=f"Pattern match: {pattern}",
                            label=self.LABEL_MAP.get(category, "AI-Other"),
                        )
                else:
                    if re.search(re.escape(pattern), normalized):
                        return ClassificationResult(
                            category=category,
                            reason=f"Keyword match: {pattern}",
                            label=self.LABEL_MAP.get(category, "AI-Other"),
                        )
        return ClassificationResult(category="Other", reason="No rule matched", label="AI-Other")

