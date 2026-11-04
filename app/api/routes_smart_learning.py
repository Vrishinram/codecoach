"""
API Router for Smart Learning Features (Phase 2)
Provides endpoints for:
1. Adaptive difficulty metrics
2. Weak-spot drill sets
3. "Explain it differently" multi-perspective tutor
4. Interactive concept map graph
5. Personal notes & SM-2 flashcard reviews
6. Study plan generation & live progress tracking
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    AdaptiveMetricsResponse, WeakSpotSummary, WeakSpotDrillResponse,
    ExplainDifferentlyRequest, ExplainDifferentlyResponse,
    ConceptMapResponse, PersonalNoteCreate, PersonalNoteResponse,
    FlashcardResponse, FlashcardReviewRequest, FlashcardReviewResponse,
    FlashcardGenerateFromMissedResponse, StudyPlanCreate, StudyPlanResponse
)
from app.services.smart_learning_service import (
    get_adaptive_metrics, get_weak_spots, create_weak_spot_drill,
    explain_concept_differently, get_concept_map_data,
    create_personal_note, list_personal_notes, delete_personal_note,
    generate_flashcards_from_missed_questions, generate_flashcards_from_note,
    get_due_flashcards, review_flashcard_sm2,
    get_study_plan_presets, create_or_update_study_plan,
    get_active_study_plan_with_progress
)
from app.models import Flashcard, StudyPlan, utc_now

logger = logging.getLogger("codecoach.api.smart_learning")
router = APIRouter(prefix="/api/smart-learning", tags=["Smart Learning"])


# ============================================================================
# 1. ADAPTIVE DIFFICULTY
# ============================================================================

@router.get("/adaptive-metrics", response_model=AdaptiveMetricsResponse)
async def get_adaptive_metrics_endpoint(
    topic_id: Optional[str] = Query(None, description="Curriculum topic ID to filter metrics for"),
    db: Session = Depends(get_db)
):
    """
    Computes per-subtopic accuracy, response time, recommended difficulty (1-5), and readiness status.
    """
    data = get_adaptive_metrics(db, topic_id=topic_id)
    return AdaptiveMetricsResponse(**data)


# ============================================================================
# 2. WEAK-SPOT DRILL
# ============================================================================

@router.get("/weak-spots", response_model=List[WeakSpotSummary])
async def get_weak_spots_endpoint(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Lists the user's top most-missed subtopics across all quiz attempts.
    """
    spots = get_weak_spots(db, limit=limit)
    return [WeakSpotSummary(**s) for s in spots]

@router.post("/weak-spot-drill", response_model=WeakSpotDrillResponse)
async def launch_weak_spot_drill(
    db: Session = Depends(get_db)
):
    """
    Generates a 10-question practice set dynamically targeting the user's most-missed subtopics.
    """
    drill_set, targeted = create_weak_spot_drill(db)
    msg = f"10-question Weak-Spot Drill generated targeting: {', '.join(targeted) if targeted else 'Core C# Concepts'}."
    return WeakSpotDrillResponse(
        set_id=drill_set.id,
        total_questions=drill_set.total_questions,
        targeted_subtopics=targeted,
        message=msg
    )


# ============================================================================
# 3. "EXPLAIN IT DIFFERENTLY"
# ============================================================================

@router.post("/explain-differently", response_model=ExplainDifferentlyResponse)
async def explain_differently_endpoint(
    payload: ExplainDifferentlyRequest,
    db: Session = Depends(get_db)
):
    """
    Re-explains any C# concept through a chosen perspective (analogy, simplified ELI5, code_first).
    Cached in database to minimize LLM token usage.
    """
    explanation, is_cached = await explain_concept_differently(
        db=db,
        concept=payload.concept,
        current_explanation=payload.current_explanation,
        perspective=payload.perspective,
        context_code=payload.context_code
    )
    return ExplainDifferentlyResponse(
        concept=payload.concept,
        perspective=payload.perspective,
        explanation=explanation,
        is_cached=is_cached
    )


# ============================================================================
# 4. CONCEPT MAP GRAPH
# ============================================================================

@router.get("/concept-map", response_model=ConceptMapResponse)
async def get_concept_map_endpoint(
    db: Session = Depends(get_db)
):
    """
    Returns the visual dependency graph of curriculum topics and user mastery states.
    """
    data = get_concept_map_data(db)
    return ConceptMapResponse(**data)


# ============================================================================
# 5. PERSONAL NOTES & FLASHCARDS (SM-2 Spaced Repetition)
# ============================================================================

@router.get("/notes", response_model=List[PersonalNoteResponse])
async def list_notes_endpoint(
    db: Session = Depends(get_db)
):
    notes = list_personal_notes(db)
    return [
        PersonalNoteResponse(
            id=n.id,
            title=n.title,
            content=n.content,
            topic_id=n.topic_id,
            tags=n.tags,
            created_at=n.created_at.isoformat(),
            updated_at=n.updated_at.isoformat()
        )
        for n in notes
    ]

@router.post("/notes", response_model=PersonalNoteResponse)
async def create_note_endpoint(
    payload: PersonalNoteCreate,
    db: Session = Depends(get_db)
):
    note = create_personal_note(
        db=db,
        title=payload.title,
        content=payload.content,
        topic_id=payload.topic_id,
        tags=payload.tags
    )
    return PersonalNoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        topic_id=note.topic_id,
        tags=note.tags,
        created_at=note.created_at.isoformat(),
        updated_at=note.updated_at.isoformat()
    )

@router.delete("/notes/{note_id}")
async def delete_note_endpoint(
    note_id: int,
    db: Session = Depends(get_db)
):
    success = delete_personal_note(db, note_id)
    if not success:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "deleted", "note_id": note_id}

@router.post("/notes/{note_id}/flashcards", response_model=List[FlashcardResponse])
async def generate_cards_from_note_endpoint(
    note_id: int,
    db: Session = Depends(get_db)
):
    cards = generate_flashcards_from_note(db, note_id)
    now = utc_now()
    return [
        FlashcardResponse(
            id=c.id,
            note_id=c.note_id,
            topic_id=c.topic_id,
            subtopic=c.subtopic,
            front=c.front,
            back=c.back,
            code_snippet=c.code_snippet,
            source_type=c.source_type,
            interval_days=c.interval_days,
            ease_factor=c.ease_factor,
            repetitions=c.repetitions,
            due_date=c.due_date.isoformat(),
            is_due=c.due_date <= now
        )
        for c in cards
    ]

@router.post("/flashcards/from-missed", response_model=FlashcardGenerateFromMissedResponse)
async def generate_cards_from_missed_endpoint(
    db: Session = Depends(get_db)
):
    """
    Zero-LLM endpoint: creates flashcards for all missed questions needing review.
    """
    cards = generate_flashcards_from_missed_questions(db)
    now = utc_now()
    card_dtos = [
        FlashcardResponse(
            id=c.id,
            note_id=c.note_id,
            topic_id=c.topic_id,
            subtopic=c.subtopic,
            front=c.front,
            back=c.back,
            code_snippet=c.code_snippet,
            source_type=c.source_type,
            interval_days=c.interval_days,
            ease_factor=c.ease_factor,
            repetitions=c.repetitions,
            due_date=c.due_date.isoformat(),
            is_due=c.due_date <= now
        )
        for c in cards
    ]
    return FlashcardGenerateFromMissedResponse(
        generated_count=len(cards),
        flashcards=card_dtos
    )

@router.get("/flashcards", response_model=List[FlashcardResponse])
async def list_all_flashcards_endpoint(
    db: Session = Depends(get_db)
):
    cards = db.query(Flashcard).order_by(Flashcard.id.desc()).all()
    now = utc_now()
    return [
        FlashcardResponse(
            id=c.id,
            note_id=c.note_id,
            topic_id=c.topic_id,
            subtopic=c.subtopic,
            front=c.front,
            back=c.back,
            code_snippet=c.code_snippet,
            source_type=c.source_type,
            interval_days=c.interval_days,
            ease_factor=c.ease_factor,
            repetitions=c.repetitions,
            due_date=c.due_date.isoformat(),
            is_due=c.due_date <= now
        )
        for c in cards
    ]

@router.get("/flashcards/due", response_model=List[FlashcardResponse])
async def list_due_flashcards_endpoint(
    db: Session = Depends(get_db)
):
    cards = get_due_flashcards(db)
    now = utc_now()
    return [
        FlashcardResponse(
            id=c.id,
            note_id=c.note_id,
            topic_id=c.topic_id,
            subtopic=c.subtopic,
            front=c.front,
            back=c.back,
            code_snippet=c.code_snippet,
            source_type=c.source_type,
            interval_days=c.interval_days,
            ease_factor=c.ease_factor,
            repetitions=c.repetitions,
            due_date=c.due_date.isoformat(),
            is_due=True
        )
        for c in cards
    ]

@router.post("/flashcards/{card_id}/review", response_model=FlashcardReviewResponse)
async def review_flashcard_endpoint(
    card_id: int,
    payload: FlashcardReviewRequest,
    db: Session = Depends(get_db)
):
    res = review_flashcard_sm2(db, card_id=card_id, rating=payload.rating)
    return FlashcardReviewResponse(**res)


# ============================================================================
# 6. STUDY PLAN GENERATOR & PROGRESS SYNC
# ============================================================================

@router.get("/study-plan/presets")
async def get_study_plan_presets_endpoint():
    """
    Returns curated study plan goal blueprints.
    """
    return get_study_plan_presets()

@router.get("/study-plan/active", response_model=Optional[StudyPlanResponse])
async def get_active_study_plan_endpoint(
    db: Session = Depends(get_db)
):
    """
    Returns current active study plan annotated with live milestone completion percentages.
    """
    plan_data = get_active_study_plan_with_progress(db)
    if not plan_data:
        return None
    return StudyPlanResponse(**plan_data)

@router.post("/study-plan", response_model=StudyPlanResponse)
async def create_study_plan_endpoint(
    payload: StudyPlanCreate,
    db: Session = Depends(get_db)
):
    """
    Generates a personalized week-by-week study plan based on target role, duration, and daily time budget.
    """
    create_or_update_study_plan(
        db=db,
        goal_title=payload.goal_title,
        target_role=payload.target_role,
        duration_weeks=payload.duration_weeks,
        daily_minutes=payload.daily_minutes
    )
    plan_data = get_active_study_plan_with_progress(db)
    return StudyPlanResponse(**plan_data)

@router.delete("/study-plan/{plan_id}")
async def deactivate_study_plan_endpoint(
    plan_id: int,
    db: Session = Depends(get_db)
):
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found")
    plan.is_active = False
    db.commit()
    return {"status": "deactivated", "plan_id": plan_id}
