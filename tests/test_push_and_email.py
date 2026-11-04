import pytest
import asyncio
from unittest.mock import MagicMock
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

