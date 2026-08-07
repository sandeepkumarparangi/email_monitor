from __future__ import annotations

import base64
import json

import pytest

from app import google_auth


def test_load_json_env_accepts_raw_json(monkeypatch):
    payload = {"installed": {"client_id": "abc"}}
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", json.dumps(payload))

    assert google_auth._load_json_env("GOOGLE_CREDENTIALS_JSON", "GOOGLE_CREDENTIALS_JSON_B64") == payload


def test_load_json_env_accepts_base64_json(monkeypatch):
    payload = {"refresh_token": "token"}
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_TOKEN_JSON_B64", base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"))

    assert google_auth._load_json_env("GOOGLE_TOKEN_JSON", "GOOGLE_TOKEN_JSON_B64") == payload


def test_get_credentials_fails_clearly_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON_B64", raising=False)
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_TOKEN_JSON_B64", raising=False)

    with pytest.raises(RuntimeError, match="Google OAuth client credentials are missing"):
        google_auth.get_credentials(
            credentials_file=str(tmp_path / "missing-credentials.json"),
            token_file=str(tmp_path / "missing-token.json"),
            scopes=["scope"],
            oauth_port=8080,
        )
