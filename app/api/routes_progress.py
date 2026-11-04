import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.database import get_db
from app.models import (
    CurriculumLevel, CurriculumTopic, TopicProgress, QuizSet,
    RetentionQuiz, TokenUsage, UserProfile, LearningLink, QuestionAttempt
)
from app.schemas import (
    DashboardStats, LevelSummary, TopicSummary, LinkItem, LinkCreate
)
from app.services.link_validator import add_custom_link, toggle_link_completed

router = APIRouter(prefix="/api", tags=["Progress & Roadmap"])
logger = logging.getLogger("codecoach.api.progress")

@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Returns all aggregated statistics for the progress dashboard.
    """
    total_topics = db.query(CurriculumTopic).count()
    mastered = db.query(TopicProgress).filter(TopicProgress.status == "Mastered").count()
    reviewing = db.query(TopicProgress).filter(TopicProgress.status == "Reviewing").count()
    learning = db.query(TopicProgress).filter(TopicProgress.status == "Learning").count()

    profile = db.query(UserProfile).first()
    streak = profile.current_streak if profile else 0
    longest_streak = profile.longest_streak if profile else 0

    # Due retention count
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    due_retention_count = db.query(RetentionQuiz).filter(
        RetentionQuiz.due_at <= now_utc,
        RetentionQuiz.completed_at == None
    ).count()

    # Missed questions needing review
    missed_count = db.query(QuestionAttempt).filter(QuestionAttempt.needs_review == True).count()
    total_due = due_retention_count + missed_count

    # Token usage
    total_tokens = db.query(func.sum(TokenUsage.total_tokens)).scalar() or 0
    
    # Tokens by model
    model_counts = db.query(TokenUsage.model, func.sum(TokenUsage.total_tokens)).group_by(TokenUsage.model).all()
    token_by_model = {m: (c or 0) for m, c in model_counts}

    # Score history (last 10 completed sets)
    recent_sets = db.query(QuizSet).filter(QuizSet.completed == True).order_by(QuizSet.id.asc()).limit(15).all()
    score_history = []
    for s in recent_sets:
        topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == s.topic_id).first()
        score_history.append({
            "set_id": s.id,
            "topic_id": s.topic_id,
            "topic_title": topic.title if topic else s.topic_id,
            "set_number": s.set_number,
            "score": round(s.score, 1),
            "passed": s.passed,
            "date": s.created_at.strftime("%b %d") if s.created_at else ""
        })

    # Due retention list
    due_retentions = db.query(RetentionQuiz).filter(
        RetentionQuiz.due_at <= now_utc,
        RetentionQuiz.completed_at == None
    ).all()
    due_ret_list = []
    for r in due_retentions:
        topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == r.topic_id).first()
        due_ret_list.append({
            "id": r.id,
            "topic_id": r.topic_id,
            "topic_title": topic.title if topic else r.topic_id,
            "stage": r.stage,
            "due_at": r.due_at.isoformat()
        })

    # Curriculum Levels & Topics
    levels = db.query(CurriculumLevel).order_by(CurriculumLevel.order).all()
    level_summaries = []
    for lvl in levels:
        t_summaries = []
        for t in lvl.topics:
            p = t.progress
            t_summaries.append(TopicSummary(
                id=t.id,
                level_id=lvl.id,
                title=t.title,
                order=t.order,
                description=t.description,
                subtopics=t.subtopics,
                status=p.status if p else "New",
                unlocked=p.unlocked if p else False,
                sets_completed=p.sets_completed if p else 0,
                highest_score=p.highest_score if p else 0.0,
                latest_score=p.latest_score if p else 0.0,
                teach_back_passed=p.teach_back_passed if p else False,
                app_challenge_passed=p.app_challenge_passed if p else False,
                retention_stage=p.retention_stage if p else 0,
                next_retention_due_at=p.next_retention_due_at.isoformat() if (p and p.next_retention_due_at) else None
            ))
        level_summaries.append(LevelSummary(
            id=lvl.id,
            title=lvl.title,
            order=lvl.order,
            description=lvl.description,
            topics=t_summaries
        ))

    return DashboardStats(
        assistant_name=settings.ASSISTANT_NAME,
        topics_total=total_topics,
        topics_mastered=mastered,
        topics_reviewing=reviewing,
        topics_learning=learning,
        current_streak=streak,
        longest_streak=longest_streak,
        due_reviews_count=total_due,
        total_tokens_used=int(total_tokens),
        token_usage_by_model=token_by_model,
        score_history=score_history,
        levels=level_summaries,
        due_retention_quizzes=due_ret_list
    )

@router.get("/curriculum", response_model=List[LevelSummary])
async def get_curriculum(db: Session = Depends(get_db)):
    """
    Returns full curriculum roadmap structure.
    """
    levels = db.query(CurriculumLevel).order_by(CurriculumLevel.order).all()
    result = []
    for lvl in levels:
        t_list = []
        for t in lvl.topics:
            p = t.progress
            t_list.append(TopicSummary(
                id=t.id,
                level_id=lvl.id,
                title=t.title,
                order=t.order,
                description=t.description,
                subtopics=t.subtopics,
                status=p.status if p else "New",
                unlocked=p.unlocked if p else False,
                sets_completed=p.sets_completed if p else 0,
                highest_score=p.highest_score if p else 0.0,
                latest_score=p.latest_score if p else 0.0,
                teach_back_passed=p.teach_back_passed if p else False,
                app_challenge_passed=p.app_challenge_passed if p else False,
                retention_stage=p.retention_stage if p else 0,
                next_retention_due_at=p.next_retention_due_at.isoformat() if (p and p.next_retention_due_at) else None
            ))
        result.append(LevelSummary(
            id=lvl.id,
            title=lvl.title,
            order=lvl.order,
            description=lvl.description,
            topics=t_list
        ))
    return result

@router.get("/links/{topic_id}", response_model=List[LinkItem])
async def get_topic_links(topic_id: str, db: Session = Depends(get_db)):
    """
    Returns verified curated and custom links for a given topic.
    """
    links = db.query(LearningLink).filter(
        LearningLink.topic_id == topic_id
    ).all()
    return [
        LinkItem(
            id=l.id,
            topic_id=l.topic_id,
            title=l.title,
            url=l.url,
            type=l.type,
            level=l.level,
            description=l.description,
            is_active=l.is_active,
            is_custom=l.is_custom,
            is_completed=l.is_completed
        ) for l in links
    ]

@router.post("/links", response_model=LinkItem)
async def create_user_custom_link(payload: LinkCreate, db: Session = Depends(get_db)):
    """
    Allows user to add custom study links in the UI.
    """
    link = add_custom_link(
        db=db,
        topic_id=payload.topic_id,
        title=payload.title,
        url=payload.url,
        link_type=payload.type,
        level=payload.level,
        description=payload.description or ""
    )
    return LinkItem(
        id=link.id,
        topic_id=link.topic_id,
        title=link.title,
        url=link.url,
        type=link.type,
        level=link.level,
        description=link.description,
        is_active=link.is_active,
        is_custom=link.is_custom,
        is_completed=link.is_completed
    )

@router.put("/links/{link_id}/toggle", response_model=LinkItem)
async def toggle_link_status(link_id: int, db: Session = Depends(get_db)):
    """
    Toggles whether a link is marked completed (watched or read).
    """
    link = toggle_link_completed(db, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return LinkItem(
        id=link.id,
        topic_id=link.topic_id,
        title=link.title,
        url=link.url,
        type=link.type,
        level=link.level,
        description=link.description,
        is_active=link.is_active,
        is_custom=link.is_custom,
        is_completed=link.is_completed
    )

