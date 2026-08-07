from __future__ import annotations

import errno
import json
import logging
import os
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
    if os.path.exists(token_file):
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
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
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
    with open(token_file, "w", encoding="utf-8") as token:
        token.write(creds.to_json())
    return creds
