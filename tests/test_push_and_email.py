import pytest
import asyncio
from unittest.mock import MagicMock
from starlette.testclient import TestClient
from pywebpush import WebPushException
from app.models import PushSubscription, NotificationLog
from app.services.push_service import send_web_push, send_ntfy_push
from app.services.email_service import send_html_email

def test_web_push_delivery_and_expired_subscription_pruning(db_session, monkeypatch):
    # Add two subscriptions: one valid, one expired
    sub1 = PushSubscription(endpoint="https://push.example.com/sub1", p256dh="key1", auth="auth1")
    sub2 = PushSubscription(endpoint="https://push.example.com/expired", p256dh="key2", auth="auth2")
    db_session.add_all([sub1, sub2])
    db_session.commit()

    # Mock webpush to simulate 410 Gone for sub2
    def mock_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        if "expired" in subscription_info["endpoint"]:
            response_mock = MagicMock()
            response_mock.status_code = 410
            raise WebPushException("Subscription has expired or is invalid", response=response_mock)
        return True

    monkeypatch.setattr("app.services.push_service.webpush", mock_webpush)

    delivered = asyncio.run(send_web_push(db_session, title="Test", body="Hello"))
    assert delivered == 1

    # Verify expired subscription was pruned
    remaining = db_session.query(PushSubscription).all()
    assert len(remaining) == 1
    assert remaining[0].endpoint == "https://push.example.com/sub1"

    # Verify logs created
    logs = db_session.query(NotificationLog).filter(NotificationLog.channel == "push").all()
    assert len(logs) == 2

def test_send_html_email_mocked(db_session, monkeypatch):
    mock_smtp_instance = MagicMock()
    mock_smtp_class = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance

    monkeypatch.setattr("smtplib.SMTP", mock_smtp_class)

    sent = send_html_email(
        db=db_session,
        to_email="student@example.com",
        subject="Daily Reminder",
        template_name="daily_reminder.html",
        context={"topic_title": "Generics", "streak": 5, "due_action_description": "Train Set #1", "due_retention_count": 0, "links": []}
    )

    assert sent is True
    # Verify log entry
    log = db_session.query(NotificationLog).filter(NotificationLog.channel == "email").first()
    assert log is not None
    assert log.status == "sent"

def test_push_subscription_validation_and_registration(client: TestClient):
    # 1. Non-HTTPS endpoint rejected
    res = client.post("/api/push/subscribe", json={
        "endpoint": "http://insecure.endpoint.com",
        "keys": {"p256dh": "BA123456789012345678901234567890123456789012", "auth": "auth123456"}
    })
    assert res.status_code == 400
    assert "HTTPS" in res.json()["detail"]

    # 2. Too short / fake keys rejected
    res = client.post("/api/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-sub-123",
        "keys": {"p256dh": "fake_short", "auth": "fake"}
    })
    assert res.status_code == 400
    assert "Malformed cryptographic keys" in res.json()["detail"]

    # 3. Valid keys accepted
    valid_p256dh = "BIPxW7F3cT_s8H1y9xK7zM6qN4aP3bC2vD1eE0fG9hI8jK7lM6nO5pQ4rS3tU2vW1xY0zA=="
    valid_auth = "auth_token_sample_123"
    res = client.post("/api/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-sub-123",
        "keys": {"p256dh": valid_p256dh, "auth": valid_auth},
        "user_agent": "Mozilla/5.0 TestBrowser"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "subscribed"

def test_push_test_diagnostics(client: TestClient, monkeypatch, db_session):
    # Mock send_ntfy_push so network call is avoided
    async def mock_ntfy(*args, **kwargs):
        return True
    monkeypatch.setattr("app.api.routes_notifications.send_ntfy_push", mock_ntfy)

    # 1. When DB has no subscriptions
    db_session.query(PushSubscription).delete()
    db_session.commit()
    res = client.post("/api/push/test")
    assert res.status_code == 200
    data = res.json()
    assert data["subscriptions_registered"] == 0
    assert data["web_push_delivered"] == 0

    # 2. When DB has a registered subscription but webpush raises WebPushException
    sub = PushSubscription(
        endpoint="https://fcm.googleapis.com/fcm/send/device-a",
        p256dh="key1234567890123456789012345",
        auth="auth12345"
    )
    db_session.add(sub)
    db_session.commit()

    def mock_failing_webpush(*args, **kwargs):
        raise WebPushException("Invalid p256dh key specified")

    monkeypatch.setattr("app.services.push_service.webpush", mock_failing_webpush)

    res = client.post("/api/push/test")
    assert res.status_code == 200
    data = res.json()
    assert data["subscriptions_registered"] == 1
    assert data["web_push_delivered"] == 0
    assert len(data["delivery_errors"]) >= 1
    assert "Invalid p256dh key" in data["delivery_errors"][0]
    assert "Found 1 registered device(s)" in data["message"]


