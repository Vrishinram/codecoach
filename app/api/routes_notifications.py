import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import PushSubscription, UserProfile
from app.schemas import PushSubscriptionCreate
from app.services.push_service import send_web_push, send_ntfy_push
from app.services.email_service import send_html_email

router = APIRouter(prefix="/api", tags=["Notifications"])
logger = logging.getLogger("codecoach.api.notifications")

class EmailTestBody(BaseModel):
    to: Optional[str] = None

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
    Validates that endpoint is an HTTPS URL and cryptographic keys are well-formed.
    """
    endpoint = (payload.endpoint or "").strip()
    if not endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid push endpoint. Must be an HTTPS URL.")

    p256dh = (payload.keys.p256dh or "").strip() if payload.keys else ""
    auth = (payload.keys.auth or "").strip() if payload.keys else ""

    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Missing Web Push cryptographic keys (p256dh and auth are required).")

    if len(p256dh) < 20 or len(auth) < 8:
        raise HTTPException(
            status_code=400,
            detail="Malformed cryptographic keys. p256dh and auth must be valid base64url keys from browser pushManager.subscribe()."
        )

    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = payload.user_agent
    else:
        sub = PushSubscription(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=payload.user_agent
        )
        db.add(sub)
    db.commit()
    from app.services.durable_store import sync_subscriptions_to_blob
    sync_subscriptions_to_blob(db)
    logger.info("Registered Web Push subscription endpoint: %s...", endpoint[:30])
    return {"status": "subscribed", "message": "Device notifications registered successfully."}

@router.post("/push/test")
async def send_test_push(db: Session = Depends(get_db)):
    """
    Sends an immediate test push to all subscribed devices and optional ntfy channel.
    Returns explicit diagnostics on registered devices, delivered pushes, and failure causes.
    """
    from app.services.durable_store import sync_subscriptions_from_blob
    sync_subscriptions_from_blob(db)

    push_stats = await send_web_push(
        db=db,
        title=f"{settings.ASSISTANT_NAME} Test Push",
        body="Congratulations! Your device notifications are active and ready for daily C# training.",
        url=f"{settings.effective_app_url}/#dashboard",
        notification_type="test",
        return_details=True
    )

    ntfy_ok = await send_ntfy_push(
        db=db,
        title=f"{settings.ASSISTANT_NAME} Test",
        body="Device notifications are active and ready for daily C# training.",
        url=f"{settings.effective_app_url}/#dashboard",
        notification_type="test"
    )

    reg = push_stats["registered"]
    deliv = push_stats["delivered"]

    if reg == 0:
        msg = "Web Push: 0 registered devices in database. Allow notifications or click 'Register This Device'."
    elif deliv > 0:
        msg = f"Test push sent! (Web Push: {deliv}/{reg} device{'s' if reg != 1 else ''} delivered, ntfy: {'Delivered' if ntfy_ok else 'Inactive'})"
    else:
        err_msg = push_stats["errors"][0] if push_stats["errors"] else "Delivery failed"
        msg = f"Found {reg} registered device(s), but Web Push failed: {err_msg}"

    return {
        "status": "success" if (deliv > 0 or ntfy_ok) else "partial",
        "subscriptions_registered": reg,
        "web_push_delivered": deliv,
        "web_push_failed": push_stats["failed"],
        "delivery_errors": push_stats["errors"],
        "ntfy_delivered": ntfy_ok,
        "storage_engine": settings.storage_engine_label,
        "message": msg
    }

@router.post("/email/test")
async def send_test_email(body: Optional[EmailTestBody] = None, db: Session = Depends(get_db)):
    """
    Sends an immediate test HTML email to USER_EMAIL or custom configured email.
    Accepts optional { "to": "..." } from Preferences. Warns if targeting @example.com.
    """
    profile = db.query(UserProfile).first()
    target_email = ((body.to if body else None) or (profile.custom_email if profile and profile.custom_email else None) or settings.USER_EMAIL or "").strip()

    from app.services.email_service import render_email_template
    context = {
        "celebration_title": "Notifications Connected!",
        "celebration_message": f"Your email reminders from {settings.ASSISTANT_NAME} are active.",
        "celebration_detail": f"You will receive daily C# training updates and weekly digests at {target_email or 'your inbox'}.",
        "app_url": settings.effective_app_url
    }
    rendered_html = render_email_template(
        "celebration.html",
        {**context, "subject": f"{settings.ASSISTANT_NAME} Test Email - Notifications Active"}
    )

    if not target_email or target_email.endswith("@example.com"):
        return JSONResponse(
            status_code=200,
            content={
                "status": "simulated",
                "delivered": False,
                "target_email": target_email or "unset",
                "message": "Set USER_EMAIL (or Preferences email) to a real address. @example.com cannot receive mail.",
                "hint": "Set USER_EMAIL (or Preferences email) to a real address. @example.com cannot receive mail.",
                "html_preview": rendered_html,
            }
        )

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return JSONResponse(
            status_code=200,
            content={
                "status": "simulated",
                "delivered": False,
                "target_email": target_email,
                "smtp_configured": False,
                "html_preview": rendered_html,
                "message": "SMTP credentials not configured in Vercel environment variables. Check SMTP_HOST, SMTP_USER, and SMTP_PASSWORD.",
                "hint": "Check SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in Vercel environment variables.",
            }
        )

    try:
        sent = send_html_email(
            db=db,
            to_email=target_email,
            subject=f"{settings.ASSISTANT_NAME} Test Email - Notifications Active",
            template_name="celebration.html",
            context=context,
            notification_type="test"
        )
        if not sent:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "simulated",
                    "delivered": False,
                    "target_email": target_email,
                    "smtp_configured": True,
                    "html_preview": rendered_html,
                    "message": f"Live SMTP failed to deliver to {target_email}. Check SMTP_HOST/PORT/USER/PASSWORD.",
                    "hint": "Check SMTP_HOST, SMTP_PORT, and SMTP_PASSWORD credentials.",
                }
            )
        return {
            "status": "success",
            "delivered": True,
            "target_email": target_email,
            "smtp_configured": True,
            "message": f"Sent to {target_email}"
        }
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "status": "simulated",
                "delivered": False,
                "target_email": target_email,
                "message": f"Live SMTP failed: {e}. Check SMTP_HOST/PORT/USER/PASSWORD.",
                "hint": f"Live SMTP exception: {e}",
                "html_preview": rendered_html,
            }
        )

