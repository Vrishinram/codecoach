import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import UserProfile
from app.schemas import SettingsUpdate

router = APIRouter(prefix="/api", tags=["Settings"])
logger = logging.getLogger("codecoach.api.settings")

@router.get("/settings")
async def get_user_settings(db: Session = Depends(get_db)):
    """
    Returns current configuration settings and reminder preferences.
    """
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
        db.commit()

    return {
        "assistant_name": settings.ASSISTANT_NAME,
        "app_url": settings.APP_URL,
        "user_email": settings.USER_EMAIL,
        "smtp_configured": bool(settings.SMTP_USER and settings.SMTP_PASSWORD),
        "vapid_configured": bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY),
        "ntfy_topic": settings.NTFY_TOPIC,
        "timezone": settings.TIMEZONE,
        "set_size": settings.SET_SIZE,
        "pass_score": settings.PASS_SCORE,
        "mastery_score": settings.MASTERY_SCORE,
        "model_name": settings.MODEL_NAME,
        "fallback_models": settings.fallback_model_list,
        # Editable preferences
        "push_enabled": profile.push_enabled,
        "email_enabled": profile.email_enabled,
        "ntfy_enabled": profile.ntfy_enabled,
        "reminders_paused": profile.reminders_paused,
        "quiet_hours_enabled": profile.quiet_hours_enabled,
        "quiet_hours_start": profile.quiet_hours_start,
        "quiet_hours_end": profile.quiet_hours_end,
        "reminder_times": profile.reminder_times or settings.REMINDER_TIMES
    }

@router.post("/settings")
async def update_user_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    """
    Updates reminder times, quiet hours, and channel toggles.
    """
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)

    if payload.push_enabled is not None:
        profile.push_enabled = payload.push_enabled
    if payload.email_enabled is not None:
        profile.email_enabled = payload.email_enabled
    if payload.ntfy_enabled is not None:
        profile.ntfy_enabled = payload.ntfy_enabled
    if payload.reminders_paused is not None:
        profile.reminders_paused = payload.reminders_paused
    if payload.quiet_hours_enabled is not None:
        profile.quiet_hours_enabled = payload.quiet_hours_enabled
    if payload.quiet_hours_start is not None:
        profile.quiet_hours_start = payload.quiet_hours_start
    if payload.quiet_hours_end is not None:
        profile.quiet_hours_end = payload.quiet_hours_end
    if payload.reminder_times is not None:
        profile.reminder_times = payload.reminder_times

    db.commit()
    return {"status": "success", "message": "Settings updated successfully."}

