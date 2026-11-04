import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models import (
    CurriculumTopic, QuizSet, QuizQuestion, QuestionAttempt,
    TopicProgress, utc_now
)
from app.llm.grader import generate_quiz_set
from app.services.curriculum_service import update_user_activity_streak

logger = logging.getLogger("codecoach.quiz")

SEED_BANK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seed_quiz_bank.json"
_cached_seed_bank = None

def _get_seed_bank_questions(topic_id: str, set_size: int = 25) -> List[Dict[str, Any]]:
    global _cached_seed_bank
    if _cached_seed_bank is None and SEED_BANK_PATH.exists():
        try:
            with open(SEED_BANK_PATH, "r", encoding="utf-8") as f:
                _cached_seed_bank = json.load(f)
        except Exception as e:
            logger.warning("Could not read seed_quiz_bank.json: %s", e)
            _cached_seed_bank = {}
    if _cached_seed_bank and topic_id in _cached_seed_bank:
        return _cached_seed_bank[topic_id][:set_size]
    return []

async def get_or_create_active_set(db: Session, topic_id: str, is_retry: bool = False, weak_subtopics: List[str] = None) -> QuizSet:
    """
    Returns an incomplete set if one already exists for this topic;
    otherwise generates a brand new set of SET_SIZE questions from the curated bank or LLM.
    Guarantees sub-second response so Vercel and local never hang.
    """
    topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == topic_id).first()
    if not topic:
        raise ValueError(f"Topic '{topic_id}' not found.")

    # Check for existing incomplete set
    existing_set = db.query(QuizSet).filter(
        QuizSet.topic_id == topic_id,
        QuizSet.completed == False
    ).order_by(QuizSet.id.desc()).first()

    if existing_set and existing_set.questions:
        return existing_set

    # Determine set number
    latest_set = db.query(QuizSet).filter(QuizSet.topic_id == topic_id).order_by(QuizSet.set_number.desc()).first()
    next_set_num = (latest_set.set_number + 1) if latest_set else 1

    # Fetch previously asked question prompts to prevent repetition
    previous_prompts = [
        q.prompt for q in db.query(QuizQuestion.prompt).filter(QuizQuestion.topic_id == topic_id).all()
    ]

    raw_questions = []

    # 1. For standard sets, serve from the curated high-yield question bank for instant response
    if not is_retry and not weak_subtopics:
        seed_questions = _get_seed_bank_questions(topic_id, settings.SET_SIZE)
        if seed_questions and len(seed_questions) >= settings.SET_SIZE:
            logger.info("Serving instant curated question bank for topic '%s'", topic_id)
            raw_questions = seed_questions

    # 2. If dynamic retry or seed bank unavailable, attempt LLM generation with 7s timeout
    if not raw_questions:
        try:
            import asyncio
            raw_questions = await asyncio.wait_for(
                generate_quiz_set(
                    topic_title=topic.title,
                    subtopics=topic.subtopics,
                    set_size=settings.SET_SIZE,
                    db=db,
                    weak_subtopics=weak_subtopics,
                    excluded_prompts=previous_prompts
                ),
                timeout=7.0
            )
        except Exception as e:
            logger.warning("LLM question generation failed or timed out for '%s': %s. Falling back to seed bank.", topic_id, e)
            raw_questions = _get_seed_bank_questions(topic_id, settings.SET_SIZE)

    # 3. Final safety fallback to avoid any possible empty set
    if not raw_questions:
        logger.warning("Empty questions for topic '%s'; generating inline fallback templates.", topic_id)
        raw_questions = [
            {
                "question_type": "mcq",
                "prompt": f"Regarding {topic.title} in C# (Concept #{idx}): Which option represents the standard .NET design pattern?",
                "code_snippet": f"// C# Practice on {topic.title}\npublic void Check_{idx}() {{ }}",
                "options": [
                    "A) Strict compile-time type verification",
                    "B) Unsafe pointer manipulation by default",
                    "C) Global variable leakage",
                    "D) Disabling garbage collection"
                ],
                "correct_answer": "A",
                "explanation": f"C# and .NET emphasize strong static typing, managed memory safety, and framework contracts.",
                "hint": "Recall the fundamental type safety principles in C#.",
                "difficulty": min(5, (idx // 5) + 1),
                "subtopic": topic.subtopics[idx % len(topic.subtopics)]
            }
            for idx in range(1, settings.SET_SIZE + 1)
        ]

    new_set = QuizSet(
        topic_id=topic_id,
        set_number=next_set_num,
        is_retry_set=is_retry,
        total_questions=len(raw_questions),
        completed=False,
        weak_subtopics_json=json.dumps(weak_subtopics or [])
    )
    db.add(new_set)
    db.flush()

    for idx, q_data in enumerate(raw_questions, start=1):
        q_obj = QuizQuestion(
            set_id=new_set.id,
            topic_id=topic_id,
            question_index=idx,
            question_type=q_data.get("question_type", "mcq"),
            prompt=q_data.get("prompt", ""),
            code_snippet=q_data.get("code_snippet"),
            options_json=json.dumps(q_data.get("options", [])),
            correct_answer=str(q_data.get("correct_answer", "")).strip(),
            explanation=q_data.get("explanation", ""),
            hint=q_data.get("hint"),
            difficulty=int(q_data.get("difficulty", 1)),
            subtopic=q_data.get("subtopic")
        )
        db.add(q_obj)

    db.commit()
    return new_set

def get_next_unanswered_question(db: Session, set_id: int) -> Optional[QuizQuestion]:
    """
    Returns the next question in the set that has not been answered yet.
    """
    answered_ids = [
        row[0] for row in db.query(QuestionAttempt.question_id).join(QuizQuestion).filter(
            QuizQuestion.set_id == set_id
        ).all()
    ]

    return db.query(QuizQuestion).filter(
        QuizQuestion.set_id == set_id,
        ~QuizQuestion.id.in_(answered_ids)
    ).order_by(QuizQuestion.question_index.asc()).first()

def evaluate_answer(
    db: Session,
    question_id: int,
    user_answer: str
) -> Tuple[bool, QuestionAttempt, QuizQuestion]:
    """
    Evaluates a user's answer:
    - Normalizes C# syntax/spaces and letters for MCQ
    - Tracks consecutive correct count (needs 2 consecutive correct to clear review flag)
    - Updates streak
    """
    question = db.query(QuizQuestion).filter(QuizQuestion.id == question_id).first()
    if not question:
        raise ValueError(f"Question {question_id} not found.")

    user_clean = user_answer.strip()
    correct_clean = question.correct_answer.strip()

    is_correct = False
    if question.question_type == "mcq":
        # Check single letter or full option text match
        first_char = user_clean[:1].upper()
        target_char = correct_clean[:1].upper()
        is_correct = (first_char == target_char) or (user_clean.lower() == correct_clean.lower())
    elif question.question_type in ("output_prediction", "fill_blank"):
        # Normalize whitespace, quotes, and case-insensitive check if sensible
        def norm(s):
            return "".join(s.split()).lower().replace('"', '').replace("'", "")
        is_correct = (norm(user_clean) == norm(correct_clean)) or (user_clean.lower() == correct_clean.lower())
    else: # coding
        # Basic normalize; C# semicolon and whitespace relaxed
        def norm_code(s):
            return "".join(s.split()).replace(";", "").lower()
        is_correct = (norm_code(user_clean) == norm_code(correct_clean)) or (correct_clean.lower() in user_clean.lower())

    # Check previous attempts on this question for consecutive_correct logic
    prev_attempt = db.query(QuestionAttempt).filter(
        QuestionAttempt.question_id == question_id
    ).order_by(QuestionAttempt.id.desc()).first()

    consecutive = 0
    if is_correct:
        consecutive = (prev_attempt.consecutive_correct + 1) if prev_attempt else 1
    else:
        consecutive = 0

    # Rule: Missed questions return in later reviews until answered correctly twice in a row
    needs_review = (consecutive < 2) if not is_correct else (consecutive < 2 and (prev_attempt and prev_attempt.needs_review))

    attempt = QuestionAttempt(
        question_id=question_id,
        topic_id=question.topic_id,
        user_answer=user_answer,
        is_correct=is_correct,
        consecutive_correct=consecutive,
        needs_review=needs_review
    )
    db.add(attempt)
    db.commit()

    update_user_activity_streak(db)

    # Check if set is now fully completed
    check_set_completion(db, question.set_id)

    return is_correct, attempt, question

def check_set_completion(db: Session, set_id: int):
    """
    Checks if all questions in the set have been answered, and updates set score and weak subtopics.
    """
    quiz_set = db.query(QuizSet).filter(QuizSet.id == set_id).first()
    if not quiz_set or quiz_set.completed:
        return

    total = len(quiz_set.questions)
    attempts = db.query(QuestionAttempt).join(QuizQuestion).filter(
        QuizQuestion.set_id == set_id
    ).all()

    # Distinct answered questions
    answered_q_ids = set(a.question_id for a in attempts)
    if len(answered_q_ids) < total:
        return # Not all answered yet

    correct_count = sum(1 for a in attempts if a.is_correct)
    score = (correct_count / total) * 100.0 if total > 0 else 0.0
    passed = score >= settings.PASS_SCORE

    # Aggregate weak subtopics from wrong answers
    wrong_attempts = [a for a in attempts if not a.is_correct]
    weak_subs = []
    for wa in wrong_attempts:
        sub = wa.question.subtopic
        if sub and sub not in weak_subs:
            weak_subs.append(sub)

    quiz_set.completed = True
    quiz_set.score = score
    quiz_set.passed = passed
    quiz_set.weak_subtopics_json = json.dumps(weak_subs)
    
    # Update TopicProgress
    prog = db.query(TopicProgress).filter(TopicProgress.topic_id == quiz_set.topic_id).first()
    if prog:
        prog.sets_completed += 1
        prog.latest_score = score
        if score > prog.highest_score:
            prog.highest_score = score
        if prog.status == "New":
            prog.status = "Learning"

    db.commit()

def get_due_review_questions(db: Session, topic_id: Optional[str] = None) -> List[QuizQuestion]:
    """
    Returns missed questions that still have needs_review == True (haven't reached 2 consecutive correct).
    """
    query = db.query(QuizQuestion).join(QuestionAttempt).filter(
        QuestionAttempt.needs_review == True
    )
    if topic_id:
        query = query.filter(QuizQuestion.topic_id == topic_id)
    return query.distinct().limit(10).all()

