from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv


DEFAULT_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
DEFAULT_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
]
DEFAULT_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


@dataclass(frozen=True)
class AppConfig:
    runtime_mode: str
    bind_host: str
    port: int
    dashboard_page_size: int
    dashboard_admin_token: Optional[str]
    local_timezone: str
    check_interval_minutes: int
    log_level: str
    google_credentials_file: str
    google_token_file: str
    google_oauth_port: int
    gmail_query: str
    gmail_max_results: int
    processed_marker_label: str
    calendar_id: str
    default_interview_duration_minutes: int
    storage_provider: str
    drive_root_folder: str
    local_backup_dir: str
    enable_llm_classifier: bool
    database_path: str
    gmail_scopes: List[str]
    calendar_scopes: List[str]
    drive_scopes: List[str]


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        runtime_mode=os.getenv("APP_RUNTIME_MODE", "worker").strip().lower(),
        bind_host=os.getenv("BIND_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        dashboard_page_size=int(os.getenv("DASHBOARD_PAGE_SIZE", "25")),
        dashboard_admin_token=os.getenv("DASHBOARD_ADMIN_TOKEN"),
        local_timezone=os.getenv("LOCAL_TIMEZONE", "America/Chicago"),
        check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "5")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        google_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        google_token_file=os.getenv("GOOGLE_TOKEN_FILE", "token.json"),
        google_oauth_port=int(os.getenv("GOOGLE_OAUTH_PORT", "8080")),
        gmail_query=os.getenv("GMAIL_QUERY", "in:inbox newer_than:14d"),
        gmail_max_results=int(os.getenv("GMAIL_MAX_RESULTS", "50")),
        processed_marker_label=os.getenv("PROCESSED_MARKER_LABEL", "Processed-By-AI-Agent"),
        calendar_id=os.getenv("CALENDAR_ID", "primary"),
        default_interview_duration_minutes=int(os.getenv("DEFAULT_INTERVIEW_DURATION_MINUTES", "60")),
        storage_provider=os.getenv("STORAGE_PROVIDER", "drive").strip().lower(),
        drive_root_folder=os.getenv("DRIVE_ROOT_FOLDER", "Job Search"),
        local_backup_dir=os.getenv("LOCAL_BACKUP_DIR", "./backup"),
        enable_llm_classifier=_bool_env("ENABLE_LLM_CLASSIFIER", "false"),
        database_path=os.getenv("DATABASE_PATH", "agent_state.db"),
        gmail_scopes=DEFAULT_GMAIL_SCOPES,
        calendar_scopes=DEFAULT_CALENDAR_SCOPES,
        drive_scopes=DEFAULT_DRIVE_SCOPES,
    )


def google_scopes(config: AppConfig) -> List[str]:
    return sorted(set(config.gmail_scopes + config.calendar_scopes + config.drive_scopes))
