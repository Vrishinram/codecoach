import base64
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from app.config import settings
from app.models import UserProfile, utc_now
from app.services.durable_store import sync_google_auth_to_blob, sync_google_auth_from_blob

logger = logging.getLogger("codecoach.google_auth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.send"
]

def is_google_oauth_configured() -> bool:
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)

def get_google_auth_url(state: str = "") -> Dict[str, Any]:
    """
    Constructs Google OAuth 2.0 authorization URL requesting gmail.send scope and offline access.
    """
    configured = is_google_oauth_configured()
    redirect_uri = settings.effective_google_redirect_uri

    if not configured:
        return {
            "configured": False,
            "url": "",
            "redirect_uri": redirect_uri,
            "message": "Google OAuth 2.0 is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in environment variables."
        }

    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state

    full_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {
        "configured": True,
        "url": full_url,
        "redirect_uri": redirect_uri
    }

def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """
    Exchanges authorization code for Google access and refresh tokens.
    """
    payload = {
        "code": code,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": settings.effective_google_redirect_uri,
        "grant_type": "authorization_code"
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "CodeCoach/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        body = he.read().decode("utf-8", errors="replace")
        logger.error("Google token exchange HTTP %d: %s", he.code, body)
        raise ValueError(f"Google token exchange failed: {body}")
    except Exception as e:
        logger.error("Google token exchange error: %s", e)
        raise ValueError(f"Google token exchange connection error: {e}")

def get_google_user_info(access_token: str) -> Dict[str, Any]:
    """
    Retrieves the user's primary email address and profile via Google UserInfo API.
    """
    req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "CodeCoach/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Failed to fetch Google UserInfo: %s", e)
        return {}

def refresh_google_access_token(db: Session, profile: UserProfile) -> Optional[str]:
    """
    Uses the saved refresh token to obtain a fresh access token from Google.
    Persists updated tokens to database and Vercel Blob store.
    """
    if not profile or not profile.google_refresh_token:
        return None

    payload = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "refresh_token": profile.google_refresh_token,
        "grant_type": "refresh_token"
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "CodeCoach/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
            new_access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)

            if new_access_token:
                profile.google_access_token = new_access_token
                profile.google_token_expiry = utc_now() + timedelta(seconds=max(expires_in - 60, 60))
                db.commit()
                sync_google_auth_to_blob(db)
                logger.info("Successfully refreshed Google OAuth access token")
                return new_access_token
    except Exception as e:
        logger.error("Failed to refresh Google access token: %s", e)
    return None

def get_valid_access_token(db: Session, profile: UserProfile) -> Optional[str]:
    """
    Returns an unexpired access token, refreshing if within 1 minute of expiry.
    """
    if not profile or not profile.google_connected:
        return None

    # Check if existing access token is still valid
    if profile.google_access_token and profile.google_token_expiry:
        if profile.google_token_expiry > (utc_now() + timedelta(seconds=60)):
            return profile.google_access_token

    # Token expired or missing, refresh using refresh_token
    return refresh_google_access_token(db, profile)

def send_email_via_gmail_api(
    db: Session,
    to_email: str,
    subject: str,
    html_content: str,
    sender_email: Optional[str] = None
) -> bool:
    """
    Sends an email directly through the Gmail REST API using the user's connected Google account.
    """
    # Restore auth from blob if needed
    sync_google_auth_from_blob(db)
    profile = db.query(UserProfile).first()
    if not profile or not profile.google_connected:
        logger.warning("Cannot send via Gmail API: Google account not connected")
        return False

    access_token = get_valid_access_token(db, profile)
    if not access_token:
        logger.error("Cannot send via Gmail API: Unable to acquire valid access token")
        return False

    from_addr = sender_email or profile.google_email or settings.EMAIL_FROM

    # Construct RFC 2822 MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")

    send_payload = json.dumps({"raw": raw_b64}).encode("utf-8")

    def _execute_send(token: str) -> bool:
        req = urllib.request.Request(
            GMAIL_SEND_URL,
            data=send_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "CodeCoach/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            msg_id = res_data.get("id")
            logger.info("Gmail API successfully sent message %s to %s", msg_id, to_email)
            return True

    try:
        return _execute_send(access_token)
    except urllib.error.HTTPError as he:
        if he.code == 401:
            # Token might have been revoked or invalidated; refresh and retry once
            logger.info("Gmail API returned 401 Unauthorized; attempting token refresh retry...")
            refreshed_token = refresh_google_access_token(db, profile)
            if refreshed_token:
                try:
                    return _execute_send(refreshed_token)
                except Exception as retry_err:
                    logger.error("Gmail API retry failed: %s", retry_err)
                    raise retry_err
        body = he.read().decode("utf-8", errors="replace")
        logger.error("Gmail API HTTP error %d: %s", he.code, body)
        raise RuntimeError(f"Gmail API error ({he.code}): {body}")
    except Exception as e:
        logger.error("Gmail API error: %s", e)
        raise

