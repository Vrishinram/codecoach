import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import PushSubscription, UserProfile
from app.schemas import PushSubscriptionCreate
from app.services.push_service import send_web_push, send_ntfy_push
from app.services.email_service import send_html_email

router = APIRouter(prefix="/api", tags=["Notifications"])
logger = logging.getLogger("codecoach.api.notifications")

@router.get("/push/public-key")
async def get_vapid_public_key():
    """
    Returns the VAPID public key needed by the browser Service Worker.
    """
    return {"publicKey": settings.VAPID_PUBLIC_KEY}

@router.post("/push/subscribe")
async def subscribe_web_push(payload: PushSubscriptionCreate, db: Session = Depends(get_db)):
    """
    Stores or updates a browser Web Push subscription.
    """
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == payload.endpoint).first()
    if existing:
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        existing.user_agent = payload.user_agent
    else:
        sub = PushSubscription(
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            user_agent=payload.user_agent
        )
        db.add(sub)
    db.commit()
    logger.info("Registered Web Push subscription endpoint: %s...", payload.endpoint[:30])
    return {"status": "subscribed", "message": "Device notifications registered successfully."}

@router.post("/push/test")
async def send_test_push(db: Session = Depends(get_db)):
    """
    Sends an immediate test push to all subscribed devices and optional ntfy channel.
    """
    push_count = await send_web_push(
        db=db,
        title=f"{settings.ASSISTANT_NAME} Test Push",
        body="Congratulations! Your device notifications are active and ready for daily C# training.",
        url=f"{settings.APP_URL}/#dashboard",
        notification_type="test"
    )

    ntfy_ok = await send_ntfy_push(
        db=db,
        title=f"{settings.ASSISTANT_NAME} Test",
        body="Device notifications are active and ready for daily C# training.",
        url=f"{settings.APP_URL}/#dashboard",
        notification_type="test"
    )

    return {
        "status": "success",
        "web_push_delivered": push_count,
        "ntfy_delivered": ntfy_ok,
        "message": f"Test push sent! (Web Push: {push_count} devices, ntfy: {ntfy_ok})"
    }

@router.post("/email/test")
async def send_test_email(db: Session = Depends(get_db)):
    """
    Sends an immediate test HTML email to USER_EMAIL.
    """
    sent = send_html_email(
        db=db,
        to_email=settings.USER_EMAIL,
        subject=f"{settings.ASSISTANT_NAME} Test Email - Notifications Active",
        template_name="celebration.html",
        context={
            "celebration_title": "Notifications Connected!",
            "celebration_message": f"Your email reminders from {settings.ASSISTANT_NAME} are active.",
            "celebration_detail": f"You will receive daily C# training updates and weekly digests at {settings.USER_EMAIL}.",
            "app_url": settings.APP_URL
        },
        notification_type="test"
    )

    if not sent:
        raise HTTPException(
            status_code=500,
            detail="Failed to send test email. Please verify SMTP_USER, SMTP_PASSWORD, and USER_EMAIL in your .env file."
        )

    return {"status": "success", "message": f"Test email sent successfully to {settings.USER_EMAIL}."}

