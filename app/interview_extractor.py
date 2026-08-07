from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from dateparser.search import search_dates

from app.models import EmailMessageData, InterviewDetails


TZ_MAP = {
    "CT": "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "UTC": "UTC",
}


class InterviewExtractor:
    def __init__(self, local_timezone: str, default_duration_minutes: int = 60) -> None:
        self.local_timezone = local_timezone
        self.default_duration_minutes = default_duration_minutes

    def extract(self, email: EmailMessageData) -> InterviewDetails:
        text = f"{email.subject}\n{email.body}"
        looks_like_interview = bool(
            re.search(r"\b(interview|interviewer|hiring manager|panel|onsite|on-site|screen)\b", text, re.I)
        )
        if not looks_like_interview:
            return InterviewDetails(is_interview=False, needs_review=False, missing_fields=[])

        recruiter_email = self._extract_email(text) or self._extract_email(email.sender)
        recruiter_name = self._extract_recruiter_name(email.sender)
        company = self._extract_company(email)
        job_title = self._extract_job_title(text)
        meeting_link = self._extract_meeting_link(text)
        phone_number = self._extract_phone(text)
        location = self._extract_location(text)
        interview_type = self._extract_interview_type(text, meeting_link, phone_number, location)
        instructions = self._extract_instructions(text)
        tz = self._extract_timezone(text) or self.local_timezone
        start, end = self._extract_start_end(text, email.received_at, tz)

        missing = []
        if not start:
            missing.append("interview_start")
        if not end:
            missing.append("interview_end_or_duration")
        if not company:
            missing.append("company")
        if not job_title:
            missing.append("job_title")

        return InterviewDetails(
            is_interview=True,
            needs_review=bool(missing),
            missing_fields=missing,
            company=company,
            job_title=job_title,
            recruiter=recruiter_name,
            recruiter_email=recruiter_email,
            interview_start=start,
            interview_end=end,
            original_timezone=tz,
            interview_type=interview_type,
            meeting_link=meeting_link,
            phone_number=phone_number,
            location=location,
            instructions=instructions,
            source_snippet=text[:1000],
        )

    def _extract_start_end(
        self,
        text: str,
        reference_dt: datetime,
        source_tz: str,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        tz = ZoneInfo(source_tz)
        base_dt = reference_dt.astimezone(tz)
        range_match = re.search(
            r"(?:from\s+)?(\d{1,2}(?::\d{2})?\s?(?:am|pm))\s*(?:to|-)\s*(\d{1,2}(?::\d{2})?\s?(?:am|pm))",
            text,
            re.I,
        )
        duration_match = re.search(r"for\s+(\d+)\s*(minute|minutes|hour|hours)", text, re.I)

        dt_candidates = search_dates(
            text,
            settings={
                "RETURN_AS_TIMEZONE_AWARE": True,
                "TIMEZONE": source_tz,
                "TO_TIMEZONE": source_tz,
                "RELATIVE_BASE": base_dt,
                "PREFER_DATES_FROM": "future",
            },
        )
        start = dt_candidates[0][1] if dt_candidates else None
        if not start:
            return None, None
        start = self.to_local_timezone(start, self.local_timezone)

        if range_match:
            end = self._parse_end_time_on_same_day(start, range_match.group(2))
            if end:
                return start, end
        if duration_match:
            qty = int(duration_match.group(1))
            unit = duration_match.group(2).lower()
            delta = timedelta(hours=qty) if "hour" in unit else timedelta(minutes=qty)
            return start, start + delta
        return start, None

    @staticmethod
    def _parse_end_time_on_same_day(start_dt: datetime, end_time_text: str) -> Optional[datetime]:
        cleaned = re.sub(r"\s+", " ", end_time_text.strip()).upper()
        for fmt in ("%I:%M %p", "%I %p"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                end = start_dt.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
                if end <= start_dt:
                    end = end + timedelta(days=1)
                return end
            except ValueError:
                continue
        return None

    @staticmethod
    def to_local_timezone(dt: datetime, local_timezone: str) -> datetime:
        if dt.tzinfo is None:
            raise ValueError("Expected timezone-aware datetime")
        return dt.astimezone(ZoneInfo(local_timezone))

    def _extract_timezone(self, text: str) -> Optional[str]:
        match = re.search(r"\b(UTC|[ECMP][SD]?T)\b", text, re.I)
        if not match:
            return None
        return TZ_MAP.get(match.group(1).upper())

    @staticmethod
    def _extract_company(email: EmailMessageData) -> Optional[str]:
        patterns = [
            r"interview with ([A-Z][A-Za-z0-9&\-\s]+)",
            r"at ([A-Z][A-Za-z0-9&\-\s]+)",
        ]
        text = f"{email.subject}\n{email.body}"
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip().rstrip(".")
        domain_match = re.search(r"@([a-zA-Z0-9\-]+)\.", email.sender)
        return domain_match.group(1).title() if domain_match else None

    @staticmethod
    def _extract_job_title(text: str) -> Optional[str]:
        match = re.search(r"(?:for|role of|position)\s+([A-Z][A-Za-z0-9/ \-]+)", text)
        return match.group(1).strip().rstrip(".") if match else None

    @staticmethod
    def _extract_email(text: str) -> Optional[str]:
        match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_recruiter_name(sender: str) -> Optional[str]:
        match = re.match(r'"?([^"<]+)"?\s*<', sender)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_meeting_link(text: str) -> Optional[str]:
        match = re.search(r"https?://[^\s)]+", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_phone(text: str) -> Optional[str]:
        match = re.search(r"(\+\d{1,3}\s?)?(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_location(text: str) -> Optional[str]:
        match = re.search(r"(?:location|address)\s*:\s*(.+)", text, re.I)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_interview_type(
        text: str,
        meeting_link: Optional[str],
        phone_number: Optional[str],
        location: Optional[str],
    ) -> str:
        lowered = text.lower()
        if "zoom" in lowered:
            return "Zoom"
        if "teams" in lowered:
            return "Teams"
        if "meet.google" in lowered or "google meet" in lowered:
            return "Google Meet"
        if location or "on-site" in lowered or "onsite" in lowered:
            return "On-site"
        if phone_number and not meeting_link:
            return "Phone"
        if meeting_link:
            return "Video"
        return "Unknown"

    @staticmethod
    def _extract_instructions(text: str) -> Optional[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        important = [ln for ln in lines if re.search(r"\b(prepare|bring|join|confirm|instructions?)\b", ln, re.I)]
        return "\n".join(important[:6]) if important else None
