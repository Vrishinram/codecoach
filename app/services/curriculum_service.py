import json
import logging
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models import (
    CurriculumLevel, CurriculumTopic, TopicProgress, UserProfile,
    RetentionQuiz, TokenUsage, QuizSet, QuestionAttempt, utc_now
)
from app.config import settings

logger = logging.getLogger("codecoach.curriculum")

def seed_curriculum_if_needed(db: Session, curriculum_path: Path = None):
    """
    Seeds the curriculum levels and topics from data/curriculum.json if database is fresh.
    """
    if db.query(CurriculumLevel).count() > 0:
        return

    if curriculum_path is None:
        curriculum_path = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum.json"

    if not curriculum_path.exists():
        logger.warning("Curriculum file not found at %s", curriculum_path)
        return

    with open(curriculum_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for lvl_idx, lvl in enumerate(data, start=1):
        level_obj = CurriculumLevel(
            id=lvl["id"],
            title=lvl["title"],
            order=lvl.get("order", lvl_idx),
            description=lvl.get("description", "")
        )
        db.add(level_obj)
        db.flush()

        for top_idx, top in enumerate(lvl.get("topics", []), start=1):
            topic_obj = CurriculumTopic(
                id=top["id"],
                level_id=level_obj.id,
                title=top["title"],
                order=top.get("order", top_idx),
                description=top.get("description", ""),
                subtopics_json=json.dumps(top.get("subtopics", []))
            )
            db.add(topic_obj)
            db.flush()

            # Initialize TopicProgress
            # First topic of first level starts unlocked, all others locked
            is_first = (lvl_idx == 1 and top_idx == 1)
            progress_obj = TopicProgress(
                topic_id=topic_obj.id,
                status="Learning" if is_first else "New",
                unlocked=is_first
            )
            db.add(progress_obj)

    # Initialize UserProfile if missing
    if not db.query(UserProfile).first():
        profile = UserProfile(
            current_streak=1,
            longest_streak=1,
            last_active_date=str(date.today()),
            reminder_times=settings.REMINDER_TIMES
        )
        db.add(profile)

    db.commit()
    logger.info("Curriculum successfully seeded.")

def update_user_activity_streak(db: Session):
    """
    Updates the daily streak for today.
    """
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
        db.flush()

    today_str = str(date.today())
    if profile.last_active_date == today_str:
        return

    if profile.last_active_date:
        last_date = datetime.strptime(profile.last_active_date, "%Y-%m-%d").date()
        diff = (date.today() - last_date).days
        if diff == 1:
            profile.current_streak += 1
            if profile.current_streak > profile.longest_streak:
                profile.longest_streak = profile.current_streak
        elif diff > 1:
            profile.current_streak = 1
    else:
        profile.current_streak = 1
        profile.longest_streak = 1

    profile.last_active_date = today_str
    db.commit()

def check_and_unlock_next_topic(db: Session, current_topic_id: str):
    """
    Rule: Next topic unlocks when the current one is at least "Reviewing".
    """
    current_topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == current_topic_id).first()
    if not current_topic:
        return

    progress = db.query(TopicProgress).filter(TopicProgress.topic_id == current_topic_id).first()
    if not progress or progress.status in ("New", "Learning"):
        # Not yet eligible to unlock next
        return

    # Find the next topic in order
    all_topics = db.query(CurriculumTopic).join(CurriculumLevel).order_by(
        CurriculumLevel.order, CurriculumTopic.order
    ).all()

    found_current = False
    for t in all_topics:
        if found_current:
            # This is the next topic
            next_prog = db.query(TopicProgress).filter(TopicProgress.topic_id == t.id).first()
            if next_prog and not next_prog.unlocked:
                next_prog.unlocked = True
                if next_prog.status == "New":
                    next_prog.status = "Learning"
                db.commit()
                logger.info("Unlocked next topic: %s", t.title)
            break
        if t.id == current_topic_id:
            found_current = True

def evaluate_topic_mastery(db: Session, topic_id: str) -> str:
    """
    Evaluates whether topic can be promoted to 'Reviewing' or 'Mastered'.
    Rules:
    - Status reaches 'Reviewing' when: Set score >= PASS_SCORE (70), AND teach-back passed, AND application challenge passed.
    - Status reaches 'Mastered' ONLY when:
      1. Set score >= MASTERY_SCORE (85)
      2. Teach-back score >= MASTERY_SCORE (85)
      3. Application challenge score >= MASTERY_SCORE (85)
      4. Spaced retention stages 1, 2, and 3 are ALL completed with score >= MASTERY_SCORE (85).
    """
    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == topic_id).first()
    if not prog:
        return "New"

    pass_threshold = settings.PASS_SCORE
    mastery_threshold = settings.MASTERY_SCORE

    set_passed = (prog.latest_score >= pass_threshold) or (prog.highest_score >= pass_threshold)
    teach_passed = prog.teach_back_passed and (prog.teach_back_score >= pass_threshold)
    app_passed = prog.app_challenge_passed and (prog.app_challenge_score >= pass_threshold)

    # Check retention quizzes
    retention_quizzes = db.query(RetentionQuiz).filter(RetentionQuiz.topic_id == topic_id).all()
    all_retention_passed = False
    if len(retention_quizzes) >= 3:
        all_retention_passed = all(
            q.completed_at is not None and q.score >= mastery_threshold
            for q in retention_quizzes
        )

    # Check for Mastered
    if (prog.highest_score >= mastery_threshold and
        prog.teach_back_score >= mastery_threshold and
        prog.app_challenge_score >= mastery_threshold and
        prog.retention_stage >= 3 and
        all_retention_passed):
        new_status = "Mastered"
    elif set_passed and teach_passed and app_passed:
        new_status = "Reviewing"
    elif prog.sets_completed > 0:
        new_status = "Learning"
    else:
        new_status = prog.status or "Learning"

    prog.status = new_status
    db.commit()

    if new_status in ("Reviewing", "Mastered"):
        check_and_unlock_next_topic(db, topic_id)

    return new_status

