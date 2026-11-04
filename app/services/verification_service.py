import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    CurriculumTopic, TopicProgress, QuizSet, TeachBackSubmission,
    ApplicationChallengeSubmission, RetentionQuiz, LearningLink, utc_now
)
from app.llm.grader import grade_teach_back, generate_app_challenge, review_app_challenge
from app.services.curriculum_service import evaluate_topic_mastery, check_and_unlock_next_topic

logger = logging.getLogger("codecoach.verification")

async def submit_teach_back(
    db: Session,
    topic_id: str,
    student_explanation: str
) -> TeachBackSubmission:
    """
    Grades student's 3-4 sentence explanation of the topic against rubric (accuracy, completeness, clarity).
    Saves submission and updates topic progress.
    """
    topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == topic_id).first()
    if not topic:
        raise ValueError(f"Topic {topic_id} not found.")

    grade_result = await grade_teach_back(
        topic_title=topic.title,
        subtopics=topic.subtopics,
        student_explanation=student_explanation,
        db=db
    )

    submission = TeachBackSubmission(
        topic_id=topic_id,
        student_explanation=student_explanation,
        accuracy_score=grade_result["accuracy_score"],
        completeness_score=grade_result["completeness_score"],
        clarity_score=grade_result["clarity_score"],
        overall_score=grade_result["overall_score"],
        missing_points_json=json.dumps(grade_result["missing_points"]),
        feedback=grade_result["feedback"],
        passed=grade_result["passed"]
    )
    db.add(submission)

    # Update TopicProgress
    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == topic_id).first()
    if prog:
        prog.teach_back_passed = grade_result["passed"]
        prog.teach_back_score = grade_result["overall_score"]
        if grade_result["passed"]:
            # If set and teach-back passed, schedule first retention quiz if not already scheduled
            schedule_initial_retention_if_eligible(db, topic_id)

    db.commit()
    evaluate_topic_mastery(db, topic_id)
    return submission

async def get_or_create_app_challenge(
    db: Session,
    topic_id: str
) -> Dict[str, str]:
    """
    Returns an application challenge prompt for practical coding verification.
    """
    topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == topic_id).first()
    if not topic:
        raise ValueError(f"Topic {topic_id} not found.")

    return await generate_app_challenge(topic.title, topic.subtopics, db=db)

async def submit_app_challenge(
    db: Session,
    topic_id: str,
    problem_prompt: str,
    student_code: str
) -> ApplicationChallengeSubmission:
    """
    Reviews practical coding challenge submission for correctness, edge cases, and style.
    """
    topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == topic_id).first()
    if not topic:
        raise ValueError(f"Topic {topic_id} not found.")

    review_result = await review_app_challenge(
        topic_title=topic.title,
        problem_prompt=problem_prompt,
        student_code=student_code,
        db=db
    )

    submission = ApplicationChallengeSubmission(
        topic_id=topic_id,
        prompt=problem_prompt,
        student_code=student_code,
        score=review_result["score"],
        correctness_notes=review_result["correctness_notes"],
        edge_case_notes=review_result["edge_case_notes"],
        style_notes=review_result["style_notes"],
        feedback=review_result["feedback"],
        passed=review_result["passed"]
    )
    db.add(submission)

    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == topic_id).first()
    if prog:
        prog.app_challenge_passed = review_result["passed"]
        prog.app_challenge_score = review_result["score"]
        if review_result["passed"]:
            schedule_initial_retention_if_eligible(db, topic_id)

    db.commit()
    evaluate_topic_mastery(db, topic_id)
    return submission

def schedule_initial_retention_if_eligible(db: Session, topic_id: str):
    """
    When a topic passes the set and verification, schedule Stage 1 retention check (1 day later).
    """
    existing = db.query(RetentionQuiz).filter(
        RetentionQuiz.topic_id == topic_id,
        RetentionQuiz.stage == 1
    ).first()
    if existing:
        return

    due_date = utc_now() + timedelta(days=1)
    rq = RetentionQuiz(
        topic_id=topic_id,
        stage=1,
        due_at=due_date,
        passed=False
    )
    db.add(rq)

    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == topic_id).first()
    if prog:
        prog.next_retention_due_at = due_date
        prog.retention_stage = 0

    db.commit()
    logger.info("Scheduled 1-day retention check for topic %s at %s", topic_id, due_date)

def advance_retention_stage(db: Session, retention_id: int, score: float) -> RetentionQuiz:
    """
    Handles completion of a retention quiz.
    Stages:
    Stage 1: 1 day -> next is Stage 2 (3 days later)
    Stage 2: 3 days -> next is Stage 3 (7 days later)
    Stage 3: 7 days -> completed!
    """
    rq = db.query(RetentionQuiz).filter(RetentionQuiz.id == retention_id).first()
    if not rq:
        raise ValueError(f"RetentionQuiz {retention_id} not found.")

    passed = score >= settings.PASS_SCORE
    rq.completed_at = utc_now()
    rq.score = score
    rq.passed = passed

    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == rq.topic_id).first()

    if passed:
        if rq.stage == 1:
            if prog:
                prog.retention_stage = 1
            # Schedule stage 2 (3 days later)
            next_due = utc_now() + timedelta(days=3)
            next_rq = RetentionQuiz(topic_id=rq.topic_id, stage=2, due_at=next_due)
            db.add(next_rq)
            if prog:
                prog.next_retention_due_at = next_due
        elif rq.stage == 2:
            if prog:
                prog.retention_stage = 2
            # Schedule stage 3 (7 days later)
            next_due = utc_now() + timedelta(days=7)
            next_rq = RetentionQuiz(topic_id=rq.topic_id, stage=3, due_at=next_due)
            db.add(next_rq)
            if prog:
                prog.next_retention_due_at = next_due
        elif rq.stage == 3:
            if prog:
                prog.retention_stage = 3
                prog.next_retention_due_at = None

    db.commit()
    evaluate_topic_mastery(db, rq.topic_id)
    return rq

def generate_learning_report(db: Session, set_id: int) -> Dict[str, Any]:
    """
    Produces the comprehensive Learning Report after completing a set.
    """
    quiz_set = db.query(QuizSet).filter(QuizSet.id == set_id).first()
    if not quiz_set:
        raise ValueError(f"QuizSet {set_id} not found.")

    topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == quiz_set.topic_id).first()
    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == quiz_set.topic_id).first()

    # Identify strengths & weak spots
    all_subtopics = topic.subtopics
    weak_subtopics = quiz_set.weak_subtopics
    strengths = [s for s in all_subtopics if s not in weak_subtopics]
    if not strengths and quiz_set.score >= 50:
        strengths = [all_subtopics[0]] if all_subtopics else ["C# Syntax & Principles"]

    # Recommended action
    if not quiz_set.passed:
        action = f"Score ({quiz_set.score:.1f}%) is below {settings.PASS_SCORE}%. A retry set focused on your weak subtopics is recommended before moving forward."
    elif not (prog and prog.teach_back_passed):
        action = "Set passed! Step 2 of Learning Verification: Explain the topic in your own words (Teach-Back challenge)."
    elif not (prog and prog.app_challenge_passed):
        action = "Teach-back verified! Step 3 of Learning Verification: Complete the practical application coding challenge."
    elif prog and prog.retention_stage < 3:
        action = f"Core verification passed! Status is 'Reviewing'. Spaced retention quizzes (1d, 3d, 7d) will unlock automatically to achieve full 'Mastered' status."
    else:
        action = "Outstanding! You have mastered this topic and passed all verification checks!"

    # Links: 2-3 articles, 1-2 videos
    articles = db.query(LearningLink).filter(
        LearningLink.topic_id == topic.id,
        LearningLink.type == "article",
        LearningLink.is_active == True
    ).limit(3).all()

    videos = db.query(LearningLink).filter(
        LearningLink.topic_id == topic.id,
        LearningLink.type == "video",
        LearningLink.is_active == True
    ).limit(2).all()

    def serialize_link(l):
        return {
            "id": l.id,
            "topic_id": l.topic_id,
            "title": l.title,
            "url": l.url,
            "type": l.type,
            "level": l.level,
            "description": l.description,
            "is_active": l.is_active,
            "is_custom": l.is_custom,
            "is_completed": l.is_completed
        }

    return {
        "topic_id": topic.id,
        "topic_title": topic.title,
        "set_number": quiz_set.set_number,
        "score": quiz_set.score,
        "passed": quiz_set.passed,
        "pass_threshold": settings.PASS_SCORE,
        "mastery_threshold": settings.MASTERY_SCORE,
        "status": prog.status if prog else "Learning",
        "strengths": strengths,
        "weak_spots": weak_subtopics,
        "teach_back_status": "Passed" if (prog and prog.teach_back_passed) else "Pending",
        "app_challenge_status": "Passed" if (prog and prog.app_challenge_passed) else "Pending",
        "retention_status": f"Stage {prog.retention_stage}/3" if prog else "None",
        "recommended_action": action,
        "start_links": [serialize_link(a) for a in articles[:2]],
        "end_links": [serialize_link(v) for v in videos] + [serialize_link(a) for a in articles[2:]]
    }

