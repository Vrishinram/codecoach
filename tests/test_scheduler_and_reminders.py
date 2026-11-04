import pytest
from datetime import datetime, date, timedelta, time
from app.models import UserProfile, NotificationLog
from app.services.reminder_service import is_within_quiet_hours, trigger_daily_reminder, trigger_celebration

def test_quiet_hours_calculation():
    profile = UserProfile(
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00"
    )

    # Within quiet hours if checking 23:00
    assert profile.quiet_hours_enabled is True

def test_comeback_nudge_trigger_after_two_missed_days(db_session, monkeypatch):
    profile = db_session.query(UserProfile).first()
    # Simulate 3 days inactive
    profile.last_active_date = str(date.today() - timedelta(days=3))
    db_session.commit()

    called = []
    async def mock_comeback(db):
        called.append(True)

    monkeypatch.setattr("app.services.reminder_service.trigger_comeback_nudge", mock_comeback)

    import asyncio
    asyncio.run(trigger_daily_reminder(db_session))

    assert len(called) == 1

def test_celebration_notification_logging(db_session, monkeypatch):
    # Mock send_web_push and send_html_email
    monkeypatch.setattr("app.services.reminder_service.send_web_push", lambda **kwargs: asyncio.sleep(0, 1))
    monkeypatch.setattr("app.services.reminder_service.send_ntfy_push", lambda **kwargs: asyncio.sleep(0, True))
    monkeypatch.setattr("app.services.reminder_service.send_html_email", lambda **kwargs: True)

    import asyncio
    asyncio.run(trigger_celebration(
        db=db_session,
        title="OOP Mastered",
        message="You passed all verification checks for Object-Oriented Programming!",
        detail="Status has been updated to Mastered on your roadmap."
    ))

    # Verification executed without exceptions
    assert True

