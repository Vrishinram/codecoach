import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.schemas import SettingsUpdate
from app.config import settings
from app.main import app

def test_settings_update_validation_valid():
    su = SettingsUpdate(
        reminder_times="08:00, 20:00",
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        user_email="batman@wayne-enterprises.com",
        ntfy_topic="gotham_patrol"
    )
    assert su.reminder_times == "08:00,20:00"
    assert su.quiet_hours_start == "22:00"
    assert su.quiet_hours_end == "07:00"
    assert su.user_email == "batman@wayne-enterprises.com"
    assert su.ntfy_topic == "gotham_patrol"

def test_settings_update_validation_invalid_reminder_times():
    with pytest.raises(ValidationError) as exc:
        SettingsUpdate(reminder_times="25:99,foo")
    assert "Invalid time" in str(exc.value)

    with pytest.raises(ValidationError):
        SettingsUpdate(reminder_times="   ")

def test_settings_update_validation_invalid_quiet_hours():
    with pytest.raises(ValidationError) as exc:
        SettingsUpdate(quiet_hours_start="99:00")
    assert "Quiet hour must be in 24h HH:MM format" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        SettingsUpdate(quiet_hours_end="invalid")
    assert "Quiet hour must be in 24h HH:MM format" in str(exc.value)

def test_settings_update_validation_invalid_email():
    with pytest.raises(ValidationError) as exc:
        SettingsUpdate(user_email="not-an-email")
    assert "Invalid email format" in str(exc.value)

def test_api_settings_get_and_post_flow(client: TestClient):
    # GET settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "effective_app_url" in data or "app_url" in data
    assert "storage_engine" in data
    assert "reminder_times" in data

    # POST invalid settings (25:99) -> 422
    bad_res = client.post("/api/settings", json={
        "reminder_times": "25:99,bad_time"
    })
    assert bad_res.status_code == 422

    # POST valid settings with custom email & ntfy topic
    good_res = client.post("/api/settings", json={
        "reminder_times": "07:30, 21:00",
        "push_enabled": True,
        "email_enabled": True,
        "ntfy_enabled": True,
        "quiet_hours_enabled": True,
        "quiet_hours_start": "23:00",
        "quiet_hours_end": "06:00",
        "user_email": "bruce@wayne.corp",
        "ntfy_topic": "batcave_signal"
    })
    assert good_res.status_code == 200

    # Re-fetch settings to verify persistence
    confirm_res = client.get("/api/settings")
    assert confirm_res.status_code == 200
    c_data = confirm_res.json()
    assert c_data["reminder_times"] == "07:30,21:00"
    assert c_data["quiet_hours_start"] == "23:00"
    assert c_data["quiet_hours_end"] == "06:00"
    assert c_data["custom_email"] == "bruce@wayne.corp"
    assert c_data["user_email"] == "bruce@wayne.corp"
    assert c_data["custom_ntfy_topic"] == "batcave_signal"

def test_api_test_email_clean_error_when_unconfigured(client: TestClient, monkeypatch):
    # Ensure SMTP credentials are empty
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")

    res = client.post("/api/email/test")
    # Must NOT be 500 internal server crash, returns simulated preview payload
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "simulated"
    assert "html_preview" in data
    assert "hint" in data

def test_config_effective_app_url_and_storage_engine(monkeypatch):
    monkeypatch.delenv("DATA_BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)

    # Test effective_app_url on Vercel
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "my-codecoach.vercel.app")
    monkeypatch.setattr(settings, "APP_URL", "http://localhost:8000")
    assert settings.effective_app_url == "https://my-codecoach.vercel.app"

    # Test storage engine label (ephemeral serverless)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:////tmp/codecoach.db")
    assert "Ephemeral" in settings.storage_engine_label

    # Test storage engine label (durable with Vercel Blob sync)
    monkeypatch.setenv("DATA_BLOB_READ_WRITE_TOKEN", "test-token")
    assert "Durable Serverless" in settings.storage_engine_label

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://user:pass@ep-cool-db.us-east-2.aws.neon.tech/codecoach")
    assert "PostgreSQL (Hosted)" in settings.storage_engine_label
