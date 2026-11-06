import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import pytest
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UserProfile, utc_now
from app.services.durable_store import (
    sync_google_auth_to_blob,
    sync_google_auth_from_blob,
    _get_fernet_cipher
)
from app.services.google_auth_service import (
    get_google_auth_url,
    is_google_oauth_configured,
    get_valid_access_token
)

def test_google_oauth_url_generation(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(settings, "APP_URL", "https://codecoach-blush.vercel.app")

    res = get_google_auth_url(state="xyz123")
    assert res["configured"] is True
    assert "https://accounts.google.com/o/oauth2/v2/auth" in res["url"]
    assert "client_id=test-client-id.apps.googleusercontent.com" in res["url"]
    assert "gmail.send" in res["url"]
    assert "access_type=offline" in res["url"]
    assert "prompt=consent" in res["url"]
    assert "state=xyz123" in res["url"]

def test_api_auth_google_url_unconfigured(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")

    res = client.get("/api/auth/google/url")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is False
    assert data["url"] == ""

def test_api_auth_google_status(client: TestClient, db_session: Session):
    profile = db_session.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db_session.add(profile)
    profile.google_connected = False
    profile.google_email = None
    db_session.commit()

    res = client.get("/api/auth/google/status")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert data["connected"] is False

def test_api_auth_google_disconnect(client: TestClient, db_session: Session):
    profile = db_session.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db_session.add(profile)
    profile.google_connected = True
    profile.google_email = "test@gmail.com"
    profile.google_refresh_token = "some-refresh-token"
    db_session.commit()

    res = client.post("/api/auth/google/disconnect")
    assert res.status_code == 200
    assert res.json()["status"] == "disconnected"

    db_session.refresh(profile)
    assert profile.google_connected is False
    assert profile.google_refresh_token is None

def test_google_auth_callback_flow(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "mock-id")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "mock-secret")

    # Mock token exchange and user info
    mock_tokens = {
        "access_token": "mock-access-token-123",
        "refresh_token": "mock-refresh-token-456",
        "expires_in": 3600
    }
    mock_user_info = {
        "email": "batman@gmail.com",
        "name": "Bruce Wayne"
    }

    with patch("app.api.routes_auth.exchange_code_for_tokens", return_value=mock_tokens), \
         patch("app.api.routes_auth.get_google_user_info", return_value=mock_user_info):

        res = client.get("/api/auth/google/callback?code=mock-auth-code", follow_redirects=False)
        assert res.status_code == 303
        assert "google=connected" in res.headers["location"]
        assert "batman%40gmail.com" in res.headers["location"]

        profile = db_session.query(UserProfile).first()
        assert profile.google_connected is True
        assert profile.google_email == "batman@gmail.com"
        assert profile.google_access_token == "mock-access-token-123"
        assert profile.google_refresh_token == "mock-refresh-token-456"

def test_test_email_via_gmail_api(client: TestClient, db_session: Session, monkeypatch):
    profile = db_session.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db_session.add(profile)
    profile.google_connected = True
    profile.google_email = "batman@gmail.com"
    profile.google_access_token = "valid-token"
    profile.google_refresh_token = "valid-refresh"
    profile.google_token_expiry = utc_now() + timedelta(hours=1)
    db_session.commit()

    with patch("app.services.google_auth_service.send_email_via_gmail_api", return_value=True):
        res = client.post("/api/email/test", json={"to": "alfred@wayne.corp"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["delivered"] is True
        assert data["provider"] == "gmail_api"
        assert data["target_email"] == "alfred@wayne.corp"

def test_fernet_auth_encryption_cycle():
    token = "test_blob_token_secret_12345"
    cipher = _get_fernet_cipher(token)
    payload = {
        "google_connected": True,
        "google_email": "tester@gmail.com",
        "google_refresh_token": "secret_refresh_token"
    }
    raw = json.dumps(payload).encode("utf-8")
    encrypted = cipher.encrypt(raw)
    assert encrypted != raw

    decrypted = json.loads(cipher.decrypt(encrypted).decode("utf-8"))
    assert decrypted["google_connected"] is True
    assert decrypted["google_email"] == "tester@gmail.com"
    assert decrypted["google_refresh_token"] == "secret_refresh_token"
