from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import AppConfig


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        local_timezone="America/Chicago",
        check_interval_minutes=5,
        log_level="INFO",
        google_credentials_file="credentials.json",
        google_token_file="token.json",
        google_oauth_port=8080,
        gmail_query="in:inbox",
        gmail_max_results=50,
        processed_marker_label="Processed-By-AI-Agent",
        calendar_id="primary",
        default_interview_duration_minutes=60,
        storage_provider="local",
        drive_root_folder="Job Search",
        local_backup_dir=str(tmp_path / "backup"),
        enable_llm_classifier=False,
        database_path=str(tmp_path / "agent_state.db"),
        gmail_scopes=[],
        calendar_scopes=[],
        drive_scopes=[],
    )


def sample_received_dt() -> datetime:
    return datetime(2026, 8, 7, 10, 0, tzinfo=ZoneInfo("America/Chicago"))

