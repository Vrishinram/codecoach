import os
import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from app.models import PushSubscription, UserProfile

logger = logging.getLogger("codecoach.durable_store")

def get_blob_token() -> str:
    return (
        os.environ.get("DATA_BLOB_READ_WRITE_TOKEN") or
        os.environ.get("BLOB_READ_WRITE_TOKEN") or
        ""
    ).strip()

def sync_subscriptions_to_blob(db: Session) -> bool:
    """
    Persists all current push subscriptions to Vercel Blob for cross-instance durability.
    """
    token = get_blob_token()
    if not token:
        return False

    subs = db.query(PushSubscription).all()
    payload = [
        {
            "endpoint": s.endpoint,
            "p256dh": s.p256dh,
            "auth": s.auth,
            "user_agent": s.user_agent
        }
        for s in subs
    ]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://blob.vercel-storage.com/subscriptions.json",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "x-add-random-suffix": "false",
            "x-access": "public"
        },
        method="PUT"
    )

    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            logger.info("Successfully synced %d subscription(s) to Vercel Blob", len(subs))
            return True
    except Exception as e:
        logger.warning("Could not sync subscriptions to Vercel Blob: %s", e)
        return False

def sync_subscriptions_from_blob(db: Session) -> int:
    """
    Restores subscriptions from Vercel Blob into the local database instance if empty.
    Returns the number of restored subscriptions.
    """
    token = get_blob_token()
    if not token:
        return 0

    # If local DB already has subscriptions, no need to overwrite
    count = db.query(PushSubscription).count()
    if count > 0:
        return count

    # Fetch from blob
    url = "https://gkteyarg56wfiy52.public.blob.vercel-storage.com/subscriptions.json"
    req = urllib.request.Request(url, headers={"User-Agent": "CodeCoach/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, list):
                return 0

            added = 0
            for item in data:
                endpoint = item.get("endpoint")
                if not endpoint:
                    continue
                existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
                if not existing:
                    sub = PushSubscription(
                        endpoint=endpoint,
                        p256dh=item.get("p256dh", ""),
                        auth=item.get("auth", ""),
                        user_agent=item.get("user_agent", "")
                    )
                    db.add(sub)
                    added += 1
            if added > 0:
                db.commit()
                logger.info("Restored %d subscription(s) from Vercel Blob", added)
            return db.query(PushSubscription).count()
    except Exception as e:
        logger.debug("No existing blob subscriptions found or fetch failed: %s", e)
        return 0
