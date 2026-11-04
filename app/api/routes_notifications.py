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
        url=f"{settings.effective_app_url}/#dashboard",
        notification_type="test"
    )

    ntfy_ok = await send_ntfy_push(
        db=db,
        title=f"{settings.ASSISTANT_NAME} Test",
        body="Device notifications are active and ready for daily C# training.",
        url=f"{settings.effective_app_url}/#dashboard",
        notification_type="test"
    )

    msg = f"Test push sent! (Web Push: {push_count} device{'s' if push_count != 1 else ''}, ntfy: {'Delivered' if ntfy_ok else 'Inactive'})"
    return {
        "status": "success",
        "web_push_delivered": push_count,
        "ntfy_delivered": ntfy_ok,
        "message": msg
    }

@router.post("/email/test")
async def send_test_email(db: Session = Depends(get_db)):
    """
    Sends an immediate test HTML email to USER_EMAIL or custom configured email.
    If SMTP credentials are unconfigured or live connection fails, returns
    an interactive HTML preview payload so user can inspect rendered transmission.
    """
    profile = db.query(UserProfile).first()
    target_email = (profile.custom_email if profile and profile.custom_email else None) or settings.USER_EMAIL

    if not target_email:
        raise HTTPException(
            status_code=400,
            detail="Destination email not configured. Please set your email in Preferences or define USER_EMAIL in your environment."
        )

    from app.services.email_service import render_email_template
    context = {
        "celebration_title": "Notifications Connected!",
        "celebration_message": f"Your email reminders from {settings.ASSISTANT_NAME} are active.",
        "celebration_detail": f"You will receive daily C# training updates and weekly digests at {target_email}.",
        "app_url": settings.effective_app_url
    }
    rendered_html = render_email_template(
        "celebration.html",
        {**context, "subject": f"{settings.ASSISTANT_NAME} Test Email - Notifications Active"}
    )

    # If SMTP credentials not provided, return clean simulated preview
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return {
            "status": "simulated",
            "delivered": False,
            "target_email": target_email,
            "smtp_configured": False,
            "html_preview": rendered_html,
            "message": f"Generated email preview for {target_email} (SMTP unconfigured).",
            "hint": "To dispatch live emails, configure valid SMTP_HOST and SMTP_PASSWORD in your Vercel project environment variables."
        }

    # Attempt live SMTP delivery
    sent = send_html_email(
        db=db,
        to_email=target_email,
        subject=f"{settings.ASSISTANT_NAME} Test Email - Notifications Active",
        template_name="celebration.html",
        context=context,
        notification_type="test"
    )

    if not sent:
        return {
            "status": "simulated",
            "delivered": False,
            "target_email": target_email,
            "smtp_configured": True,
            "html_preview": rendered_html,
            "message": f"Live SMTP connection failed for {target_email}. Generated interactive email preview.",
            "hint": "Check SMTP_HOST, SMTP_PORT (e.g. 587 or 465), and SMTP_PASSWORD (e.g. Google 16-character App Password)."
        }

    return {
        "status": "success",
        "delivered": True,
        "target_email": target_email,
        "smtp_configured": True,
        "message": f"Test email sent successfully to {target_email}."
    }

