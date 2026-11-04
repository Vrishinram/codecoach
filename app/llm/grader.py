import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TokenUsage
from app.llm.client import llm_client
from app.llm.prompts import (
    get_educator_system_prompt,
    get_quiz_generation_prompt,
    get_teach_back_grading_prompt,
    get_app_challenge_generation_prompt,
    get_app_challenge_review_prompt,
    get_placement_test_generation_prompt
)

logger = logging.getLogger("codecoach.grader")

def _record_token_usage(db: Session, model: str, usage: Dict[str, Any], operation: str):
    try:
        tu = TokenUsage(
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            operation=operation
        )
        db.add(tu)
        db.commit()
    except Exception as e:
        logger.error("Failed to record token usage: %s", e)
        db.rollback()

async def generate_quiz_set(
    topic_title: str,
    subtopics: List[str],
    set_size: int,
    db: Session,
    weak_subtopics: List[str] = None,
    excluded_prompts: List[str] = None
) -> List[Dict[str, Any]]:
    prompt = get_quiz_generation_prompt(
        topic_title=topic_title,
        subtopics=subtopics,
        set_size=set_size,
        weak_subtopics=weak_subtopics,
        excluded_prompts=excluded_prompts
    )
    result = await llm_client.generate_validated_json(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=get_educator_system_prompt(),
        max_tokens=8192
    )
    _record_token_usage(db, result["model"], result["usage"], "generate_quiz")
    data = result["data"]
    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]
    if not isinstance(data, list):
        raise ValueError("LLM did not return a list of questions.")
    return data

async def grade_teach_back(
    topic_title: str,
    subtopics: List[str],
    student_explanation: str,
    db: Session
) -> Dict[str, Any]:
    prompt = get_teach_back_grading_prompt(topic_title, subtopics, student_explanation)
    result = await llm_client.generate_validated_json(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=get_educator_system_prompt(),
        max_tokens=1000
    )
    _record_token_usage(db, result["model"], result["usage"], "grade_teach_back")
    data = result["data"]
    
    # Ensure all required keys exist
    overall = float(data.get("overall_score", 0.0))
    passed = bool(data.get("passed", overall >= settings.PASS_SCORE))
    return {
        "accuracy_score": float(data.get("accuracy_score", 0.0)),
        "completeness_score": float(data.get("completeness_score", 0.0)),
        "clarity_score": float(data.get("clarity_score", 0.0)),
        "overall_score": overall,
        "passed": passed,
        "missing_points": data.get("missing_points", []),
        "feedback": data.get("feedback", "No feedback provided.")
    }

async def generate_app_challenge(
    topic_title: str,
    subtopics: List[str],
    db: Session
) -> Dict[str, str]:
    prompt = get_app_challenge_generation_prompt(topic_title, subtopics)
    result = await llm_client.generate_validated_json(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=get_educator_system_prompt(),
        max_tokens=1000
    )
    _record_token_usage(db, result["model"], result["usage"], "generate_app_challenge")
    return {
        "topic_id": topic_title,
        "prompt": result["data"].get("prompt", ""),
        "starter_code": result["data"].get("starter_code", "public class Solution\n{\n    \n}")
    }

async def review_app_challenge(
    topic_title: str,
    problem_prompt: str,
    student_code: str,
    db: Session
) -> Dict[str, Any]:
    prompt = get_app_challenge_review_prompt(topic_title, problem_prompt, student_code)
    result = await llm_client.generate_validated_json(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=get_educator_system_prompt(),
        max_tokens=1500
    )
    _record_token_usage(db, result["model"], result["usage"], "review_app_challenge")
    data = result["data"]
    score = float(data.get("score", 0.0))
    passed = bool(data.get("passed", score >= settings.PASS_SCORE))
    return {
        "score": score,
        "passed": passed,
        "correctness_notes": data.get("correctness_notes", ""),
        "edge_case_notes": data.get("edge_case_notes", ""),
        "style_notes": data.get("style_notes", ""),
        "feedback": data.get("feedback", "")
    }

async def generate_placement_questions(db: Session) -> List[Dict[str, Any]]:
    prompt = get_placement_test_generation_prompt()
    result = await llm_client.generate_validated_json(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=get_educator_system_prompt(),
        max_tokens=2500
    )
    _record_token_usage(db, result["model"], result["usage"], "placement")
    data = result["data"]
    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]
    return data

