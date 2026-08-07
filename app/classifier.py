from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.models import ClassificationResult, EmailMessageData


class EmailClassifier:
    CATEGORY_RULES: List[Tuple[str, List[str]]] = [
        ("Interview / Interview Invitation", ["interview", "panel", "onsite", "on-site", "schedule"]),
        ("Assessment / HackerRank / Coding Test", ["hackerrank", "codility", "assessment", "coding test"]),
        ("Offer", ["offer letter", "compensation", "we are excited to offer"]),
        ("Rejection", ["unfortunately", "not moving forward", "regret to inform"]),
        ("Job Application Update", ["application status", "your application", "next steps"]),
        ("Recruiter / Job Opportunity", ["recruiter", "opportunity", "role", "position"]),
        ("Work / Professional", ["project", "client", "meeting agenda", "sprint"]),
        ("Finance", ["invoice", "payment", "statement", "bank"]),
        ("Promotions", ["unsubscribe", "sale", "discount", "promo"]),
        ("Spam / Unimportant", ["lottery", "winner", "claim prize", "urgent transfer"]),
        ("Personal", ["family", "party", "dinner", "vacation"]),
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
        for category, keywords in self.CATEGORY_RULES:
            if any(re.search(rf"\b{re.escape(keyword)}\b", normalized) for keyword in keywords):
                return ClassificationResult(
                    category=category,
                    reason=f"Keyword match: {keywords}",
                    label=self.LABEL_MAP.get(category, "AI-Other"),
                )
        return ClassificationResult(category="Other", reason="No rule matched", label="AI-Other")

