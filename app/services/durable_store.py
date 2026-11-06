import os
import json
import base64
import hashlib
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Optional
from cryptography.fernet import Fernet

from sqlalchemy.orm import Session
from app.models import PushSubscription, UserProfile

logger = logging.getLogger("codecoach.durable_store")

def get_blob_token() -> str:
    return (
        os.environ.get("DATA_BLOB_READ_WRITE_TOKEN") or
        os.environ.get("BLOB_READ_WRITE_TOKEN") or
        ""
    ).strip()

def _get_fernet_cipher(token: str) -> Fernet:
    key_material = hashlib.sha256(f"codecoach_blob_auth_enc_{token}".encode("utf-8")).digest()
    urlsafe_key = base64.urlsafe_b64encode(key_material)
    return Fernet(urlsafe_key)

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

def sync_google_auth_to_blob(db: Session) -> bool:
    """
    Encrypts and persists Google OAuth tokens to Vercel Blob for durable multi-instance auth.
    """
    token = get_blob_token()
    if not token:
        return False

    profile = db.query(UserProfile).first()
    if not profile:
        return False

    payload = {
        "google_connected": bool(profile.google_connected),
        "google_email": profile.google_email,
        "google_access_token": profile.google_access_token,
        "google_refresh_token": profile.google_refresh_token,
        "google_token_expiry": profile.google_token_expiry.isoformat() if profile.google_token_expiry else None,
        "updated_at": datetime.utcnow().isoformat()
    }

    try:
        cipher = _get_fernet_cipher(token)
        encrypted_bytes = cipher.encrypt(json.dumps(payload).encode("utf-8"))

        req = urllib.request.Request(
            "https://blob.vercel-storage.com/google_auth.enc",
            data=encrypted_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "x-add-random-suffix": "false",
                "x-access": "public"
            },
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            logger.info("Successfully persisted encrypted Google OAuth state to Vercel Blob")
            return True
    except Exception as e:
        logger.warning("Could not sync Google OAuth state to Vercel Blob: %s", e)
        return False

def sync_google_auth_from_blob(db: Session) -> bool:
    """
    Restores encrypted Google OAuth credentials from Vercel Blob if missing in local instance.
    Returns True if user is connected with Google.
    """
    token = get_blob_token()
    if not token:
        return False

    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
        db.commit()

    # If already loaded with valid refresh token, no need to re-fetch
    if profile.google_connected and profile.google_refresh_token:
        return True

    url = "https://gkteyarg56wfiy52.public.blob.vercel-storage.com/google_auth.enc"
    req = urllib.request.Request(url, headers={"User-Agent": "CodeCoach/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            encrypted_data = resp.read()
            if not encrypted_data:
                return False

            cipher = _get_fernet_cipher(token)
            raw_json = cipher.decrypt(encrypted_data).decode("utf-8")
            data = json.loads(raw_json)

            profile.google_connected = bool(data.get("google_connected", False))
            profile.google_email = data.get("google_email")
            profile.google_access_token = data.get("google_access_token")
            profile.google_refresh_token = data.get("google_refresh_token")
            
            expiry_str = data.get("google_token_expiry")
            if expiry_str:
                try:
                    profile.google_token_expiry = datetime.fromisoformat(expiry_str)
                except Exception:
                    profile.google_token_expiry = None
            else:
                profile.google_token_expiry = None

            db.commit()
            logger.info("Restored Google OAuth credentials from Vercel Blob (connected: %s)", profile.google_connected)
            return bool(profile.google_connected and profile.google_refresh_token)
    except Exception as e:
        logger.debug("Could not restore Google auth from Vercel Blob: %s", e)
        return False


