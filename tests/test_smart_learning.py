"""
Unit and Integration Tests for Phase 2: Smart Learning Features
Verifies:
1. Adaptive difficulty engine (rule-based difficulty scaling 1-5 without LLM)
2. Weak-spot drill set generation (10 questions focusing on weakest subtopics)
3. "Explain it differently" multi-perspective caching and generation
4. Interactive concept map data structure and mastery evaluation
5. Personal notes storage and retrieval
6. SM-2 spaced repetition flashcard review schedule
7. Zero-LLM flashcards generation from missed quiz attempts
8. Study plan generation and live curriculum milestone progress
"""

import pytest
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    CurriculumLevel, CurriculumTopic, TopicProgress, QuizSet,
    QuizQuestion, QuestionAttempt, PersonalNote, Flashcard,
    StudyPlan, ExplanationCache, utc_now
)
from app.services.smart_learning_service import (
    calculate_adaptive_difficulty_for_subtopic, get_adaptive_metrics,
    get_weak_spots, create_weak_spot_drill,
    explain_concept_differently, get_concept_map_data,
    create_personal_note, list_personal_notes, delete_personal_note,
    generate_flashcards_from_missed_questions, generate_flashcards_from_note,
    get_due_flashcards, review_flashcard_sm2,
    get_study_plan_presets, create_or_update_study_plan,
    get_active_study_plan_with_progress
)

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed test level and topics
    lvl = CurriculumLevel(id="csharp-basics", title="C# Basics", order=1)
    db.add(lvl)
    db.flush()

    top1 = CurriculumTopic(
        id="variables-and-types",
        level_id="csharp-basics",
        title="Variables & Data Types",
        order=1,
        subtopics_json=json.dumps(["value vs reference types", "primitive types", "nullable types"])
    )
    top2 = CurriculumTopic(
        id="operators-and-expressions",
        level_id="csharp-basics",
        title="Operators & Expressions",
        order=2,
        subtopics_json=json.dumps(["null-coalescing (?? and ??=)", "comparison & logical"])
    )
    db.add_all([top1, top2])
    db.flush()

    prog1 = TopicProgress(topic_id="variables-and-types", status="Learning", unlocked=True, highest_score=75.0, sets_completed=1)
    prog2 = TopicProgress(topic_id="operators-and-expressions", status="New", unlocked=False)
    db.add_all([prog1, prog2])
    db.commit()

    try:
        yield db
    finally:
        db.close()


def test_adaptive_difficulty_rule_scaling():
    # 1. High accuracy + fast response time -> Level 5 (Master)
    diff, label, readiness = calculate_adaptive_difficulty_for_subtopic(
        total_attempts=10, correct_attempts=10, avg_response_time_ms=5000
    )
    assert diff == 5
    assert "Level 5" in label
    assert "Mastered" in readiness

    # 2. Strong accuracy (90%) -> Level 4
    diff, label, readiness = calculate_adaptive_difficulty_for_subtopic(
        total_attempts=10, correct_attempts=9, avg_response_time_ms=12000
    )
    assert diff == 4

    # 3. Moderate accuracy (75%) -> Level 3
    diff, label, readiness = calculate_adaptive_difficulty_for_subtopic(
        total_attempts=8, correct_attempts=6, avg_response_time_ms=20000
    )
    assert diff == 3

    # 4. Struggling accuracy (30%) -> Level 1 (Foundations)
    diff, label, readiness = calculate_adaptive_difficulty_for_subtopic(
        total_attempts=10, correct_attempts=3, avg_response_time_ms=45000
    )
    assert diff == 1
    assert "Needs Remediation" in readiness


def test_weak_spot_drill_generation(test_db):
    # Create questions and failed attempts
    qset = QuizSet(topic_id="variables-and-types", set_number=1, total_questions=3, completed=True)
    test_db.add(qset)
    test_db.flush()

    q1 = QuizQuestion(
        set_id=qset.id,
        topic_id="variables-and-types",
        question_index=1,
        question_type="mcq",
        prompt="Explain struct vs class memory allocation",
        options_json=json.dumps(["A) Stack vs Heap", "B) None"]),
        correct_answer="A",
        explanation="Structs live on stack or inline; classes live on heap.",
        subtopic="value vs reference types"
    )
    test_db.add(q1)
    test_db.flush()

    # User failed this question
    att1 = QuestionAttempt(
        question_id=q1.id,
        topic_id="variables-and-types",
        user_answer="B",
        is_correct=False,
        needs_review=True,
        response_time_ms=22000
    )
    test_db.add(att1)
    test_db.commit()

    # Verify weak spot identification
    weak_spots = get_weak_spots(test_db)
    assert len(weak_spots) >= 1
    assert weak_spots[0]["subtopic"] == "value vs reference types"
    assert weak_spots[0]["miss_count"] == 1

    # Create 10-question Weak-Spot Drill
    drill_set, targeted = create_weak_spot_drill(test_db)
    assert drill_set.is_retry_set is True
    assert drill_set.total_questions == 10
    assert "value vs reference types" in targeted

    # Verify questions are populated in DB
    drill_questions = test_db.query(QuizQuestion).filter(QuizQuestion.set_id == drill_set.id).all()
    assert len(drill_questions) == 10


@pytest.mark.asyncio
async def test_explain_concept_differently_caching(test_db):
    # Test pre-curated dictionary returns instantly with is_cached=True
    text, is_cached = await explain_concept_differently(
        db=test_db,
        concept="Span<T> in C#",
        current_explanation="Span represents contiguous memory",
        perspective="analogy"
    )
    assert is_cached is True
    assert "magnifying glass" in text.lower() or "library" in text.lower()

    # Test code_first perspective for record types
    code_text, is_cached = await explain_concept_differently(
        db=test_db,
        concept="record types",
        current_explanation="Records give value equality",
        perspective="code_first"
    )
    assert is_cached is True
    assert "public record" in code_text


def test_concept_map_graph_structure(test_db):
    map_data = get_concept_map_data(test_db)
    assert "nodes" in map_data
    assert "edges" in map_data
    assert map_data["total_nodes"] == 2
    assert map_data["learning_nodes"] == 1
    assert map_data["locked_nodes"] == 1

    # Check node fields
    vnode = next(n for n in map_data["nodes"] if n["id"] == "variables-and-types")
    assert vnode["title"] == "Variables & Data Types"
    assert vnode["status"] == "Learning"
    assert vnode["unlocked"] is True


def test_personal_notes_crud(test_db):
    note = create_personal_note(
        db=test_db,
        title="Span<T> vs Memory<T>",
        content="Span cannot be boxed or used across async awaits. Use Memory<T> instead.",
        topic_id="arrays-and-spans",
        tags=["Performance", "Memory"]
    )
    assert note.id is not None
    assert note.title == "Span<T> vs Memory<T>"
    assert "Performance" in note.tags

    notes = list_personal_notes(test_db)
    assert len(notes) == 1

    # Generate flashcard from note
    cards = generate_flashcards_from_note(test_db, note.id)
    assert len(cards) >= 1
    assert cards[0].note_id == note.id

    # Delete note
    deleted = delete_personal_note(test_db, note.id)
    assert deleted is True
    assert len(list_personal_notes(test_db)) == 0


def test_sm2_spaced_repetition_flashcards(test_db):
    card = Flashcard(
        topic_id="variables-and-types",
        front="What is boxing in C#?",
        back="Converting a value type to object type on the managed heap.",
        interval_days=1,
        ease_factor=2.5,
        repetitions=0,
        due_date=utc_now() - timedelta(minutes=5)
    )
    test_db.add(card)
    test_db.commit()

    # Check due query
    due_cards = get_due_flashcards(test_db)
    assert len(due_cards) == 1
    assert due_cards[0].id == card.id

    # 1. Review rating 3 (Good) -> repetition 1, interval 1
    res1 = review_flashcard_sm2(test_db, card.id, rating=3)
    assert res1["repetitions"] == 1
    assert res1["new_interval_days"] == 1

    # 2. Second review rating 3 (Good) -> repetition 2, interval 3
    res2 = review_flashcard_sm2(test_db, card.id, rating=3)
    assert res2["repetitions"] == 2
    assert res2["new_interval_days"] == 3

    # 3. Third review rating 4 (Easy) -> interval expands with ease bonus
    res3 = review_flashcard_sm2(test_db, card.id, rating=4)
    assert res3["repetitions"] == 3
    assert res3["new_interval_days"] >= 6

    # 4. Review rating 1 (Again / Missed) -> interval resets to 1, repetition resets to 0
    res4 = review_flashcard_sm2(test_db, card.id, rating=1)
    assert res4["repetitions"] == 0
    assert res4["new_interval_days"] == 1


def test_auto_generate_flashcards_from_missed_questions(test_db):
    qset = QuizSet(topic_id="variables-and-types", set_number=1, total_questions=1)
    test_db.add(qset)
    test_db.flush()

    q = QuizQuestion(
        set_id=qset.id,
        topic_id="variables-and-types",
        question_index=1,
        question_type="mcq",
        prompt="Which keyword declares an immutable record type in C# 9+?",
        options_json=json.dumps(["A) record", "B) struct", "C) static", "D) const"]),
        correct_answer="A",
        explanation="The record keyword generates value-based equality semantics.",
        subtopic="record types"
    )
    test_db.add(q)
    test_db.flush()

    att = QuestionAttempt(
        question_id=q.id,
        topic_id="variables-and-types",
        user_answer="B",
        is_correct=False,
        needs_review=True
    )
    test_db.add(att)
    test_db.commit()

    # Auto-generate flashcards
    cards = generate_flashcards_from_missed_questions(test_db)
    assert len(cards) == 1
    assert cards[0].front == q.prompt
    assert "A" in cards[0].back
    assert "Correct Answer" in cards[0].back
    assert cards[0].source_type == "missed_question"


def test_study_plan_generation_and_progress_sync(test_db):
    presets = get_study_plan_presets()
    assert len(presets) >= 2

    # Create Junior .NET 8-week plan
    plan = create_or_update_study_plan(
        db=test_db,
        goal_title="Junior .NET Developer in 8 Weeks",
        target_role="Junior .NET Developer",
        duration_weeks=8,
        daily_minutes=30
    )
    assert plan.id is not None
    assert plan.duration_weeks == 8
    assert len(plan.weeks) == 8

    # Query with progress
    active_plan = get_active_study_plan_with_progress(test_db)
    assert active_plan is not None
    assert active_plan["goal_title"] == "Junior .NET Developer in 8 Weeks"
    assert len(active_plan["weeks"]) == 8
    assert active_plan["weeks"][0]["completed"] is False # Week 1 has incomplete topics
