import logging
from datetime import datetime, timezone, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    CurriculumTopic, TopicProgress, RetentionQuiz, UserProfile,
    LearningLink, QuizSet, NotificationLog, utc_now
)
from app.services.push_service import send_web_push, send_ntfy_push
from app.services.email_service import send_html_email

logger = logging.getLogger("codecoach.reminder")

def is_within_quiet_hours(profile: UserProfile) -> bool:
    """
    Checks if current local time is within configured quiet hours.
    """
    if not profile or not profile.quiet_hours_enabled:
        return False

    try:
        now_time = datetime.now().time()
        start = datetime.strptime(profile.quiet_hours_start, "%H:%M").time()
        end = datetime.strptime(profile.quiet_hours_end, "%H:%M").time()
        if start <= end:
            return start <= now_time <= end
        else: # Crosses midnight
            return now_time >= start or now_time <= end
    except Exception as e:
        logger.error("Error evaluating quiet hours: %s", e)
        return False

async def trigger_daily_reminder(db: Session, forced: bool = False):
    """
    Orchestrates the scheduled daily reminder.
    1. Checks if paused or in quiet hours (unless forced).
    2. Checks for 2 missed days -> triggers gentle comeback nudge instead.
    3. Finds active topic, due set or review quiz, streak, and due spaced retentions.
    4. Dispatches both Web Push (and ntfy) and HTML email.
    """
    profile = db.query(UserProfile).first()
    if profile and profile.reminders_paused and not forced:
        logger.info("Reminders currently paused by user.")
        return

    if profile and is_within_quiet_hours(profile) and not forced:
        logger.info("Currently in quiet hours; skipping scheduled notification.")
        return

    # Check for 2+ missed days (comeback nudge)
    if profile and profile.last_active_date:
        last_active = datetime.strptime(profile.last_active_date, "%Y-%m-%d").date()
        days_inactive = (date.today() - last_active).days
        if days_inactive >= 2 and not forced:
            await trigger_comeback_nudge(db)
            return

    # Determine current active topic
    active_progress = db.query(TopicProgress).filter(
        TopicProgress.unlocked == True,
        TopicProgress.status != "Mastered"
    ).first()

    if not active_progress:
        # Fallback to first topic
        active_progress = db.query(TopicProgress).first()

    topic = active_progress.topic if active_progress else None
    topic_title = topic.title if topic else "C# Fundamentals"
    topic_id = topic.id if topic else "variables-and-types"

    # Check due retention quizzes
    now_utc = utc_now()
    due_retention = db.query(RetentionQuiz).filter(
        RetentionQuiz.due_at <= now_utc,
        RetentionQuiz.completed_at == None
    ).all()
    due_retention_count = len(due_retention)

    # Determine action description and deep link
    if due_retention_count > 0:
        due_action = f"Spaced retention quiz due for {due_retention[0].topic_id}"
        deep_link = f"{settings.APP_URL}/#retention"
    elif active_progress and active_progress.status == "Learning":
        due_action = f"Set #{active_progress.current_set_number} ready to train"
        deep_link = f"{settings.APP_URL}/#quiz/{topic_id}"
    elif active_progress and active_progress.status == "Reviewing":
        if not active_progress.teach_back_passed:
            due_action = f"Teach-Back explanation needed for {topic_title}"
            deep_link = f"{settings.APP_URL}/#teach-back/{topic_id}"
        elif not active_progress.app_challenge_passed:
            due_action = f"Application coding challenge ready for {topic_title}"
            deep_link = f"{settings.APP_URL}/#app-challenge/{topic_id}"
        else:
            due_action = f"Spaced retention countdown active for {topic_title}"
            deep_link = f"{settings.APP_URL}/#roadmap"
    else:
        due_action = "Daily C# practice session is ready"
        deep_link = f"{settings.APP_URL}/#dashboard"

    # Curated links for topic
    links = db.query(LearningLink).filter(
        LearningLink.topic_id == topic_id,
        LearningLink.is_active == True
    ).limit(2).all()

    streak = profile.current_streak if profile else 1

    # 1. Send Web Push
    if not profile or profile.push_enabled:
        push_body = f"Today: {topic_title} • {due_action}"
        if due_retention_count > 0:
            push_body += f" ({due_retention_count} reviews due)"
        await send_web_push(
            db=db,
            title=f"{settings.ASSISTANT_NAME}: Daily C# Training",
            body=push_body,
            url=deep_link,
            notification_type="daily_reminder"
        )

    # 2. Send ntfy fallback push
    if not profile or profile.ntfy_enabled:
        await send_ntfy_push(
            db=db,
            title=f"{settings.ASSISTANT_NAME}: {topic_title}",
            body=due_action,
            url=deep_link,
            notification_type="daily_reminder"
        )

    # 3. Send HTML Email
    if not profile or profile.email_enabled:
        email_context = {
            "subject": f"C# Daily Reminder: {topic_title} ({streak} Day Streak)",
            "topic_title": topic_title,
            "due_action_description": due_action,
            "streak": streak,
            "due_retention_count": due_retention_count,
            "links": [{"title": l.title, "url": l.url, "type": l.type} for l in links],
            "app_url": deep_link
        }
        send_html_email(
            db=db,
            to_email=settings.USER_EMAIL,
            subject=email_context["subject"],
            template_name="daily_reminder.html",
            context=email_context,
            notification_type="daily_reminder"
        )

async def trigger_comeback_nudge(db: Session):
    """
    Sends a friendly comeback nudge after 2 missed days.
    """
    profile = db.query(UserProfile).first()
    active_progress = db.query(TopicProgress).filter(TopicProgress.unlocked == True, TopicProgress.status != "Mastered").first()
    topic_title = active_progress.topic.title if active_progress and active_progress.topic else "C# Fundamentals"

    # Push
    await send_web_push(
        db=db,
        title=f"We miss you at {settings.ASSISTANT_NAME}!",
        body=f"Keep your C# momentum alive! 5 minutes on {topic_title} is waiting.",
        url=f"{settings.APP_URL}/#dashboard",
        notification_type="comeback_nudge"
    )
    if not profile or profile.ntfy_enabled:
        await send_ntfy_push(
            db=db,
            title="Keep your C# momentum alive!",
            body=f"5 minutes on {topic_title} is ready.",
            url=f"{settings.APP_URL}/#dashboard",
            notification_type="comeback_nudge"
        )

    # Email
    if not profile or profile.email_enabled:
        send_html_email(
            db=db,
            to_email=settings.USER_EMAIL,
            subject=f"Keep your C# momentum alive - {settings.ASSISTANT_NAME}",
            template_name="comeback_nudge.html",
            context={"topic_title": topic_title, "app_url": settings.APP_URL},
            notification_type="comeback_nudge"
        )

async def trigger_celebration(db: Session, title: str, message: str, detail: str):
    """
    Sends celebration notification when a topic is Mastered or a streak milestone is reached.
    """
    profile = db.query(UserProfile).first()
    # Push
    await send_web_push(
        db=db,
        title=f"🎉 Milestone Achieved! - {settings.ASSISTANT_NAME}",
        body=message,
        url=f"{settings.APP_URL}/#dashboard",
        notification_type="celebration"
    )
    if not profile or profile.ntfy_enabled:
        await send_ntfy_push(
            db=db,
            title="🎉 Milestone Achieved!",
            body=message,
            url=f"{settings.APP_URL}/#dashboard",
            notification_type="celebration"
        )

    # Email
    if not profile or profile.email_enabled:
        send_html_email(
            db=db,
            to_email=settings.USER_EMAIL,
            subject=f"🏆 Milestone Reached: {title}",
            template_name="celebration.html",
            context={
                "celebration_title": title,
                "celebration_message": message,
                "celebration_detail": detail,
                "app_url": settings.APP_URL
            },
            notification_type="celebration"
        )

async def trigger_weekly_summary(db: Session):
    """
    Aggregates stats for the past 7 days and dispatches the weekly summary email.
    """
    seven_days_ago = utc_now() - timedelta(days=7)
    recent_sets = db.query(QuizSet).filter(QuizSet.completed == True, QuizSet.created_at >= seven_days_ago).all()
    
    sets_completed = len(recent_sets)
    avg_score = round(sum(s.score for s in recent_sets) / sets_completed, 1) if sets_completed > 0 else 0.0
    mastered_count = db.query(TopicProgress).filter(TopicProgress.status == "Mastered").count()

    # Collect weak subtopics
    weak_topics = set()
    for s in recent_sets:
        for w in s.weak_subtopics:
            weak_topics.add(w)

    next_topic = db.query(CurriculumTopic).join(TopicProgress).filter(
        TopicProgress.unlocked == True,
        TopicProgress.status != "Mastered"
    ).first()
    next_topic_title = next_topic.title if next_topic else "Advanced Architecture & Testing"

    context = {
        "sets_completed": sets_completed,
        "average_score": avg_score,
        "topics_mastered": mastered_count,
        "weak_topics": list(weak_topics)[:5],
        "next_week_topic": next_topic_title,
        "app_url": settings.APP_URL
    }

    send_html_email(
        db=db,
        to_email=settings.USER_EMAIL,
        subject=f"{settings.ASSISTANT_NAME} Weekly Summary: {sets_completed} Sets Completed",
        template_name="weekly_summary.html",
        context=context,
        notification_type="weekly_summary"
    )

