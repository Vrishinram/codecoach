import logging
import urllib.parse
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import UserProfile, utc_now
from app.services.google_auth_service import (
    is_google_oauth_configured,
    get_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_info
)
from app.services.durable_store import sync_google_auth_to_blob, sync_google_auth_from_blob

logger = logging.getLogger("codecoach.api.auth")
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.get("/google/url")
async def get_auth_url():
    """
    Returns the Google OAuth 2.0 authorization URL for client redirect.
    """
    return get_google_auth_url()

@router.get("/google/callback")
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    OAuth 2.0 redirect target from Google consent screen.
    Exchanges code for tokens, extracts user identity, and updates UserProfile.
    """
    if error:
        logger.warning("Google OAuth error callback: %s", error)
        err_param = urllib.parse.quote_plus(error)
        return RedirectResponse(url=f"/#settings?google=error&detail={err_param}", status_code=303)

    if not code:
        logger.warning("Google OAuth callback received without code")
        return RedirectResponse(url="/#settings?google=error&detail=Missing+authorization+code", status_code=303)

    try:
        tokens = exchange_code_for_tokens(code)
    except Exception as e:
        logger.error("Token exchange failed during Google callback: %s", e)
        err_msg = urllib.parse.quote_plus(str(e)[:120])
        return RedirectResponse(url=f"/#settings?google=error&detail={err_msg}", status_code=303)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Retrieve user email
    user_info = get_google_user_info(access_token)
    user_email = user_info.get("email") or settings.USER_EMAIL

    # Fetch or initialize UserProfile
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)

    profile.google_connected = True
    profile.google_email = user_email
    profile.google_access_token = access_token
    if refresh_token:
        profile.google_refresh_token = refresh_token
    profile.google_token_expiry = utc_now() + timedelta(seconds=max(expires_in - 60, 60))

    # Also set default custom_email if not set
    if not profile.custom_email:
        profile.custom_email = user_email

    db.commit()

    # Sync encrypted tokens to Vercel Blob
    sync_google_auth_to_blob(db)

    logger.info("Successfully connected Google Account for %s (refresh_token present: %s)", user_email, bool(refresh_token))
    email_param = urllib.parse.quote_plus(user_email or "")
    return RedirectResponse(url=f"/#settings?google=connected&email={email_param}", status_code=303)

@router.get("/google/status")
async def get_google_auth_status(db: Session = Depends(get_db)):
    """
    Returns current Google account connection telemetry.
    """
    sync_google_auth_from_blob(db)
    profile = db.query(UserProfile).first()
    connected = bool(profile and profile.google_connected and profile.google_refresh_token)

    return {
        "configured": is_google_oauth_configured(),
        "connected": connected,
        "email": profile.google_email if (profile and connected) else "",
        "redirect_uri": settings.effective_google_redirect_uri
    }

@router.post("/google/disconnect")
async def disconnect_google_account(db: Session = Depends(get_db)):
    """
    Clears connected Google credentials from database and Vercel Blob.
    """
    profile = db.query(UserProfile).first()
    if profile:
        profile.google_connected = False
        profile.google_email = None
        profile.google_access_token = None
        profile.google_refresh_token = None
        profile.google_token_expiry = None
        db.commit()

    sync_google_auth_to_blob(db)
    logger.info("Google Account disconnected by user")
    return {"status": "disconnected", "message": "Google account disconnected successfully."}

