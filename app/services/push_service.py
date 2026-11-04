import json
import logging
from typing import Optional, Dict, Any, List
import httpx
from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PushSubscription, NotificationLog, utc_now

logger = logging.getLogger("codecoach.push")

async def send_web_push(
    db: Session,
    title: str,
    body: str,
    url: Optional[str] = None,
    notification_type: str = "daily_reminder"
) -> int:
    """
    Sends Web Push to all registered device subscriptions via pywebpush with VAPID keys.
    Automatically prunes expired/unregistered endpoints (HTTP 404, 410).
    Logs attempts and returns count of successfully delivered push notifications.
    """
    subscriptions = db.query(PushSubscription).all()
    if not subscriptions:
        logger.info("No Web Push subscriptions registered.")
        return 0

    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not configured in .env; Web Push skipped.")
        return 0

    target_url = url or settings.APP_URL
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": f"{settings.APP_URL}/static/icons/icon-192.png",
        "badge": f"{settings.APP_URL}/static/icons/icon-192.png",
        "data": {
            "url": target_url
        }
    })

    sent_count = 0
    expired_ids = []

    for sub in subscriptions:
        sub_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth
            }
        }
        status = "failed"
        error_msg = None

        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT}
            )
            sent_count += 1
            status = "sent"
        except WebPushException as ex:
            error_msg = str(ex)
            # Response code 404 or 410 means subscription expired or was revoked by browser
            if ex.response and ex.response.status_code in (404, 410):
                logger.info("Subscription expired (HTTP %d). Pruning endpoint.", ex.response.status_code)
                expired_ids.append(sub.id)
            else:
                logger.error("Web Push error: %s", ex)
        except Exception as e:
            error_msg = str(e)
            logger.error("Unexpected error sending Web Push: %s", e)

        log = NotificationLog(
            channel="push",
            notification_type=notification_type,
            subject=title,
            content=f"{body} | URL: {target_url}",
            status=status,
            error_message=error_msg,
            sent_at=utc_now()
        )
        db.add(log)

    # Prune expired subscriptions
    if expired_ids:
        db.query(PushSubscription).filter(PushSubscription.id.in_(expired_ids)).delete(synchronize_session=False)

    db.commit()
    return sent_count

async def send_ntfy_push(
    db: Session,
    title: str,
    body: str,
    url: Optional[str] = None,
    notification_type: str = "daily_reminder"
) -> bool:
    """
    Sends notification to an optional ntfy.sh topic as an effortless phone fallback channel.
    Requires no app install or VAPID setup on phones.
    """
    if not settings.NTFY_TOPIC:
        return False

    target_url = url or settings.APP_URL
    endpoint = f"https://ntfy.sh/{settings.NTFY_TOPIC}"
    status = "failed"
    error_msg = None

    headers = {
        "Title": title,
        "Click": target_url,
        "Tags": "books,mortar_board,bell"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(endpoint, data=body.encode("utf-8"), headers=headers)
            if resp.status_code < 400:
                status = "sent"
            else:
                error_msg = f"ntfy HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to send ntfy push: %s", e)

    log = NotificationLog(
        channel="ntfy",
        notification_type=notification_type,
        subject=title,
        content=f"{body} | URL: {target_url}",
        status=status,
        error_message=error_msg,
        sent_at=utc_now()
    )
    db.add(log)
    db.commit()
    return status == "sent"

