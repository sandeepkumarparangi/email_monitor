from __future__ import annotations

import errno
import base64
import json
import logging
import os
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


def get_credentials(
    credentials_file: str,
    token_file: str,
    scopes: Sequence[str],
    oauth_port: int,
) -> Credentials:
    creds: Credentials | None = None
    token_info = _load_json_env("GOOGLE_TOKEN_JSON", "GOOGLE_TOKEN_JSON_B64")
    if token_info is not None:
        try:
            creds = Credentials.from_authorized_user_info(token_info, scopes)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("GOOGLE_TOKEN_JSON(_B64) is present but invalid JSON credentials data.") from exc
    elif os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, scopes)
        except (json.JSONDecodeError, ValueError):
            logging.warning("Invalid token file at %s. Re-running OAuth flow.", token_file)
            creds = None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if creds and not creds.has_scopes(scopes):
        logging.warning("Existing token is missing required scopes. Re-running OAuth flow.")
        creds = None
    if not creds or not creds.valid:
        client_config = _load_json_env("GOOGLE_CREDENTIALS_JSON", "GOOGLE_CREDENTIALS_JSON_B64")
        if client_config is not None:
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
        elif os.path.exists(credentials_file):
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
        else:
            raise RuntimeError(
                "Google OAuth client credentials are missing. Set GOOGLE_CREDENTIALS_JSON or "
                "GOOGLE_CREDENTIALS_JSON_B64 on Railway, or provide GOOGLE_CREDENTIALS_FILE locally."
            )
        if not _can_run_interactive_oauth():
            raise RuntimeError(
                "No valid Google token is available for this non-interactive environment. "
                "Set GOOGLE_TOKEN_JSON or GOOGLE_TOKEN_JSON_B64 with a previously authorized token."
            )
        try:
            creds = flow.run_local_server(port=oauth_port)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            logging.warning(
                "OAuth port %s is in use; retrying with an automatically assigned free port.",
                oauth_port,
            )
            creds = flow.run_local_server(port=0)
    Path(token_file).parent.mkdir(parents=True, exist_ok=True)
    with open(token_file, "w", encoding="utf-8") as token:
        token.write(creds.to_json())
    return creds


def _load_json_env(raw_name: str, b64_name: str) -> dict | None:
    raw_value = os.getenv(raw_name)
    if raw_value:
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{raw_name} is set but is not valid JSON.") from exc
    encoded_value = os.getenv(b64_name)
    if encoded_value:
        try:
            decoded = base64.b64decode(encoded_value).decode("utf-8")
            return json.loads(decoded)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"{b64_name} is set but is not valid base64-encoded JSON.") from exc
    return None


def _can_run_interactive_oauth() -> bool:
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        return False
    return os.getenv("ALLOW_INTERACTIVE_OAUTH", "true").strip().lower() in {"1", "true", "yes", "on"}
