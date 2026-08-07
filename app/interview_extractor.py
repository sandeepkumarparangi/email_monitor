from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from dateparser.search import search_dates

from app.models import DownloadedAttachment, EmailMessageData, InterviewDetails


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

INTERVIEW_RE = re.compile(
    r"\b(interview|interviewer|hiring manager|panel|onsite|on-site|screen|recruiter screen|technical screen)\b",
    re.I,
)
UPDATE_RE = re.compile(
    r"\b(reschedule|rescheduled|rescheduling|updated schedule|schedule update|moved to|new time|time change|updated interview)\b",
    re.I,
)
AVAILABILITY_RE = re.compile(
    r"\b(?:share|send|provide|confirm)\b.{0,40}\bavailability\b|\bwhen are you available\b|\bwhat times work\b",
    re.I | re.S,
)
GENERIC_COMPANIES = {"Zoom", "Teams", "Google", "Meet", "Interview"}


class InterviewExtractor:
    def __init__(self, local_timezone: str, default_duration_minutes: int = 60) -> None:
        self.local_timezone = local_timezone
        self.default_duration_minutes = default_duration_minutes

    def extract(
        self,
        email: EmailMessageData,
        attachments: Optional[list[DownloadedAttachment]] = None,
    ) -> InterviewDetails:
        ics_fields = self._extract_ics_fields(attachments or [], email.received_at)
        text = self._build_source_text(email, ics_fields)
        looks_like_interview = bool(INTERVIEW_RE.search(text) or ics_fields)
        if not looks_like_interview:
            return InterviewDetails(is_interview=False, needs_review=False, missing_fields=[])

        recruiter_email = (
            self._value(ics_fields.get("organizer_email"), self._extract_email(text), self._extract_email(email.sender))
        )
        recruiter_name = self._value(ics_fields.get("organizer_name"), self._extract_recruiter_name(email.sender))
        company = self._value(
            ics_fields.get("company"),
            self._extract_company(email, text),
            self._extract_company_from_summary(str(ics_fields.get("summary") or "")),
        )
        job_title = self._value(
            ics_fields.get("job_title"),
            self._extract_job_title(text),
            self._extract_job_title(str(ics_fields.get("summary") or "")),
        )
        meeting_link = self._value(ics_fields.get("meeting_link"), self._extract_meeting_link(text))
        phone_number = self._extract_phone(text)
        location = self._value(ics_fields.get("location"), self._extract_location(text))
        interview_type = self._extract_interview_type(text, meeting_link, phone_number, location)
        instructions = self._extract_instructions(text)
        tz = self._value(
            ics_fields.get("timezone"),
            self._extract_timezone(text),
            self.local_timezone,
        )
        start, end = self._extract_start_end(text, email.received_at, tz)
        start = self._value(ics_fields.get("interview_start"), start)
        end = self._value(ics_fields.get("interview_end"), end)
        if start and not end and not AVAILABILITY_RE.search(text):
            end = start + timedelta(minutes=self.default_duration_minutes)

        action = "schedule"
        update_detected = bool(UPDATE_RE.search(text) or (ics_fields.get("sequence_number") or 0) > 0)
        if AVAILABILITY_RE.search(text) and not start:
            action = "availability"
        elif update_detected:
            action = "update"

        details = InterviewDetails(
            is_interview=True,
            needs_review=False,
            missing_fields=[],
            action=action,
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
            update_detected=update_detected,
            review_reason=None,
            calendar_uid=ics_fields.get("uid"),
            calendar_method=ics_fields.get("method"),
            source_kind="ics" if ics_fields else "email",
            source_snippet=text[:1000],
        )
        return self.refresh_review_state(details)

    def merge_with_existing(self, details: InterviewDetails, existing: InterviewDetails) -> InterviewDetails:
        preserve_existing_schedule = details.action == "schedule" and not details.update_detected
        merged = InterviewDetails(
            is_interview=details.is_interview or existing.is_interview,
            needs_review=False,
            missing_fields=[],
            action=details.action,
            company=details.company or existing.company,
            job_title=details.job_title or existing.job_title,
            recruiter=details.recruiter or existing.recruiter,
            recruiter_email=details.recruiter_email or existing.recruiter_email,
            interview_start=details.interview_start or (existing.interview_start if preserve_existing_schedule else None),
            interview_end=details.interview_end or (existing.interview_end if preserve_existing_schedule else None),
            original_timezone=details.original_timezone or existing.original_timezone,
            interview_type=details.interview_type or existing.interview_type,
            meeting_link=details.meeting_link or existing.meeting_link,
            phone_number=details.phone_number or existing.phone_number,
            location=details.location or existing.location,
            instructions=details.instructions or existing.instructions,
            update_detected=details.update_detected,
            review_reason=details.review_reason,
            calendar_uid=details.calendar_uid or existing.calendar_uid,
            calendar_method=details.calendar_method or existing.calendar_method,
            source_kind=details.source_kind or existing.source_kind,
            source_snippet=details.source_snippet or existing.source_snippet,
        )
        return self.refresh_review_state(merged)

    def refresh_review_state(self, details: InterviewDetails) -> InterviewDetails:
        missing = []
        if not details.interview_start:
            missing.append("interview_start")
        if not details.interview_end:
            missing.append("interview_end_or_duration")
        if not details.company:
            missing.append("company")
        if not details.job_title:
            missing.append("job_title")

        review_reason = details.review_reason
        if details.action == "availability" and not review_reason:
            review_reason = "Candidate availability requested but no confirmed interview time was provided."
        if missing and not review_reason:
            review_reason = f"Missing fields: {', '.join(missing)}"

        return InterviewDetails(
            is_interview=details.is_interview,
            needs_review=bool(missing) or details.action == "availability",
            missing_fields=missing,
            action=details.action,
            company=details.company,
            job_title=details.job_title,
            recruiter=details.recruiter,
            recruiter_email=details.recruiter_email,
            interview_start=details.interview_start,
            interview_end=details.interview_end,
            original_timezone=details.original_timezone,
            interview_type=details.interview_type,
            meeting_link=details.meeting_link,
            phone_number=details.phone_number,
            location=details.location,
            instructions=details.instructions,
            review_reason=review_reason,
            update_detected=details.update_detected,
            calendar_uid=details.calendar_uid,
            calendar_method=details.calendar_method,
            source_kind=details.source_kind,
            source_snippet=details.source_snippet,
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
    def _value(*values: object) -> object:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
        return None

    @staticmethod
    def _build_source_text(email: EmailMessageData, ics_fields: dict[str, Any]) -> str:
        parts = [
            email.subject,
            email.body,
            str(ics_fields.get("summary") or ""),
            str(ics_fields.get("description") or ""),
            str(ics_fields.get("location") or ""),
        ]
        return "\n".join(part for part in parts if part)

    def _extract_ics_fields(
        self,
        attachments: list[DownloadedAttachment],
        reference_dt: datetime,
    ) -> dict[str, Any]:
        for attachment in attachments:
            if not self._looks_like_ics(attachment):
                continue
            parsed = self._parse_ics_content(attachment.content, reference_dt)
            if parsed:
                return parsed
        return {}

    @staticmethod
    def _looks_like_ics(attachment: DownloadedAttachment) -> bool:
        lowered_name = attachment.filename.lower()
        lowered_type = attachment.mime_type.lower()
        return lowered_name.endswith(".ics") or "calendar" in lowered_type or lowered_type == "text/plain"

    def _parse_ics_content(self, raw: bytes, reference_dt: datetime) -> dict[str, Any]:
        text = raw.decode("utf-8", errors="replace")
        unfolded = self._unfold_ics_lines(text)
        in_event = False
        method: Optional[str] = None
        fields: dict[str, Any] = {}
        for line in unfolded:
            if not line:
                continue
            if line.startswith("METHOD:"):
                method = line.split(":", 1)[1].strip().upper()
                continue
            if line == "BEGIN:VEVENT":
                in_event = True
                continue
            if line == "END:VEVENT":
                break
            if not in_event or ":" not in line:
                continue
            meta, value = line.split(":", 1)
            name, params = self._parse_ics_meta(meta)
            value = self._unescape_ics_text(value.strip())
            if name == "UID":
                fields["uid"] = value
            elif name == "SUMMARY":
                fields["summary"] = value
            elif name == "DESCRIPTION":
                fields["description"] = value
            elif name == "LOCATION":
                fields["location"] = value
            elif name == "SEQUENCE":
                fields["sequence_number"] = int(value) if value.isdigit() else 0
            elif name == "ORGANIZER":
                organizer_name = params.get("CN")
                organizer_email = value.replace("mailto:", "").replace("MAILTO:", "")
                fields["organizer_name"] = organizer_name
                fields["organizer_email"] = organizer_email
            elif name == "DTSTART":
                parsed = self._parse_ics_datetime(value, params, reference_dt)
                if parsed:
                    fields["interview_start"] = self.to_local_timezone(parsed, self.local_timezone)
                    fields["timezone"] = parsed.tzinfo.key if isinstance(parsed.tzinfo, ZoneInfo) else "UTC"
            elif name == "DTEND":
                parsed = self._parse_ics_datetime(value, params, reference_dt)
                if parsed:
                    fields["interview_end"] = self.to_local_timezone(parsed, self.local_timezone)
            elif name == "DURATION":
                fields["duration"] = self._parse_ics_duration(value)
        if method:
            fields["method"] = method
        if fields.get("interview_start") and not fields.get("interview_end") and fields.get("duration"):
            fields["interview_end"] = fields["interview_start"] + fields["duration"]
        combined_text = "\n".join(str(fields.get(key) or "") for key in ("summary", "description", "location"))
        fields["meeting_link"] = self._extract_meeting_link(combined_text)
        fields["company"] = self._extract_company_from_summary(str(fields.get("summary") or ""))
        fields["job_title"] = self._extract_job_title(combined_text)
        return fields

    @staticmethod
    def _unfold_ics_lines(text: str) -> list[str]:
        unfolded: list[str] = []
        for line in text.splitlines():
            if line.startswith((" ", "\t")) and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line.rstrip("\r"))
        return unfolded

    @staticmethod
    def _parse_ics_meta(meta: str) -> Tuple[str, dict[str, str]]:
        parts = meta.split(";")
        name = parts[0].upper()
        params: dict[str, str] = {}
        for item in parts[1:]:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            params[key.upper()] = value.strip('"')
        return name, params

    @staticmethod
    def _parse_ics_duration(value: str) -> timedelta:
        match = re.fullmatch(r"P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)", value)
        if not match:
            return timedelta(minutes=0)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    @staticmethod
    def _parse_ics_datetime(value: str, params: dict[str, str], reference_dt: datetime) -> Optional[datetime]:
        if params.get("VALUE") == "DATE":
            parsed = datetime.strptime(value, "%Y%m%d")
            tz = reference_dt.tzinfo or ZoneInfo("UTC")
            return parsed.replace(tzinfo=tz)
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
        if len(value) == 15:
            parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
        elif len(value) == 13:
            parsed = datetime.strptime(value, "%Y%m%dT%H%M")
        else:
            return None
        tz_name = params.get("TZID")
        tz = ZoneInfo(tz_name) if tz_name else (reference_dt.tzinfo or ZoneInfo("UTC"))
        return parsed.replace(tzinfo=tz)

    @staticmethod
    def _unescape_ics_text(value: str) -> str:
        return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")

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
    def _extract_company(email: EmailMessageData, text: str) -> Optional[str]:
        patterns = [
            r"interview with ([A-Z][A-Za-z0-9&\-\s]+?)(?:\s+for\b|[,\.\n]|$)",
            r"\bat ([A-Z][A-Za-z0-9&\-\s]+?)(?:\s+for\b|[,\.\n]|$)",
            r"\bfrom ([A-Z][A-Za-z0-9&\-\s]+?)(?:\s+for\b|[,\.\n]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                company = match.group(1).strip().rstrip(".")
                if company not in GENERIC_COMPANIES:
                    return company
        domain_match = re.search(r"@([a-zA-Z0-9\-]+)\.", email.sender)
        return domain_match.group(1).title() if domain_match else None

    def _extract_company_from_summary(self, text: str) -> Optional[str]:
        patterns = [
            r"interview with ([A-Z][A-Za-z0-9&\-\s]+?)(?:\s+for\b|[,\.\n]|$)",
            r"([A-Z][A-Za-z0-9&\-\s]+?) interview",
            r"invite: ([A-Z][A-Za-z0-9&\-\s]+?)(?:\s+for\b|[,\.\n]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                company = match.group(1).strip().rstrip(".")
                if company not in GENERIC_COMPANIES:
                    return company
        return None

    @staticmethod
    def _extract_job_title(text: str) -> Optional[str]:
        patterns = [
            r"for\s+(?:the\s+)?(?:position|job id|requisition)\s+(?:\d+\s+[-:]?\s*)?([A-Z][A-Za-z0-9/ \-]+?)(?:[,\.\n]| via\b| at\b|$)",
            r"(?:position|job id|requisition)\s+(?:\d+\s+[-:]?\s*)?([A-Z][A-Za-z0-9/ \-]+?)(?:[,\.\n]| via\b| at\b|$)",
            r"(?:for|role of|candidate for)\s+([A-Z][A-Za-z0-9/ \-]+?)(?:[,\.\n]| via\b| at\b|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip().rstrip(".")
        return None

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
        urls = re.findall(r"https?://[^\s)]+", text)
        if not urls:
            return None
        preferred_domains = ("zoom.us", "teams.microsoft.com", "meet.google.com", "webex.com", "hirevue.com")
        for url in urls:
            if any(domain in url.lower() for domain in preferred_domains):
                return url
        return urls[0]

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
        if "webex" in lowered:
            return "Webex"
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
        important = [ln for ln in lines if re.search(r"\b(prepare|bring|join|confirm|instructions?|agenda|resume)\b", ln, re.I)]
        return "\n".join(important[:6]) if important else None
