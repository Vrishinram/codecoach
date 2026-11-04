import json
import logging
from pathlib import Path
from typing import List, Optional
import httpx
from sqlalchemy.orm import Session

from app.models import LearningLink, utc_now

logger = logging.getLogger("codecoach.links")

def seed_links_if_needed(db: Session, links_path: Path = None):
    """
    Seeds curated verified links from data/links.json if database has no links.
    """
    if db.query(LearningLink).count() > 0:
        return

    if links_path is None:
        links_path = Path(__file__).resolve().parent.parent.parent / "data" / "links.json"

    if not links_path.exists():
        logger.warning("links.json not found at %s", links_path)
        return

    with open(links_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        link = LearningLink(
            topic_id=item["topic_id"],
            title=item["title"],
            url=item["url"],
            type=item.get("type", "article"),
            level=item.get("level", "beginner"),
            description=item.get("description", ""),
            is_active=True,
            is_custom=False,
            is_completed=False,
            last_checked_at=utc_now()
        )
        db.add(link)

    db.commit()
    logger.info("Successfully seeded %d curated learning links.", len(data))

async def validate_single_link(client: httpx.AsyncClient, link: LearningLink, db: Session) -> bool:
    """
    Performs an HTTP HEAD or GET request to verify the URL responds with a 2xx or 3xx status.
    Flags broken ones (is_active = False).
    """
    try:
        # Standard browser user-agent to prevent bot-blocking
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CodeCoach/1.0"}
        resp = await client.head(link.url, headers=headers, follow_redirects=True, timeout=10.0)
        
        # If method not allowed for HEAD, fallback to GET with byte range
        if resp.status_code == 405:
            resp = await client.get(link.url, headers={**headers, "Range": "bytes=0-100"}, follow_redirects=True, timeout=10.0)

        is_active = (resp.status_code < 400)
    except Exception as e:
        logger.debug("Link check failed for %s: %s", link.url, e)
        is_active = False

    link.is_active = is_active
    link.last_checked_at = utc_now()
    return is_active

async def validate_all_links(db: Session) -> int:
    """
    Scans all learning links and updates their active status. Run on startup and daily by scheduler.
    """
    links = db.query(LearningLink).all()
    if not links:
        return 0

    active_count = 0
    async with httpx.AsyncClient(verify=False) as client:
        for link in links:
            is_active = await validate_single_link(client, link, db)
            if is_active:
                active_count += 1

    db.commit()
    logger.info("Link validation complete: %d / %d links active.", active_count, len(links))
    return active_count

def add_custom_link(
    db: Session,
    topic_id: str,
    title: str,
    url: str,
    link_type: str = "article",
    level: str = "beginner",
    description: str = ""
) -> LearningLink:
    """
    Allows user to add their own study link via the UI.
    """
    link = LearningLink(
        topic_id=topic_id,
        title=title,
        url=url,
        type=link_type,
        level=level,
        description=description,
        is_active=True,
        is_custom=True,
        is_completed=False,
        last_checked_at=utc_now()
    )
    db.add(link)
    db.commit()
    return link

def toggle_link_completed(db: Session, link_id: int) -> Optional[LearningLink]:
    """
    Allows user to mark an article or video as read/watched.
    """
    link = db.query(LearningLink).filter(LearningLink.id == link_id).first()
    if link:
        link.is_completed = not link.is_completed
        db.commit()
    return link

