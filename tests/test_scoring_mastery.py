import pytest
from app.models import (
    QuizSet, QuizQuestion, QuestionAttempt, TopicProgress, RetentionQuiz, utc_now
)
from app.services.quiz_service import evaluate_answer, check_set_completion
from app.services.curriculum_service import evaluate_topic_mastery, check_and_unlock_next_topic

def test_answer_evaluation_and_consecutive_correct(db_session):
    # Setup test question
    q = QuizQuestion(
        set_id=1,
        topic_id="variables-and-types",
        question_index=1,
        question_type="mcq",
        prompt="What is int in C#?",
        options_json='["A) Value type", "B) Reference type"]',
        correct_answer="A",
        explanation="int is a System.Int32 struct (value type)."
    )
    db_session.add(q)
    db_session.commit()

    # Wrong answer
    is_correct, attempt1, _ = evaluate_answer(db_session, q.id, "B")
    assert not is_correct
    assert attempt1.consecutive_correct == 0
    assert attempt1.needs_review is True

    # First correct answer (still needs 2 consecutive)
    is_correct, attempt2, _ = evaluate_answer(db_session, q.id, "A")
    assert is_correct
    assert attempt2.consecutive_correct == 1
    assert attempt2.needs_review is True

    # Second consecutive correct answer (clears review flag)
    is_correct, attempt3, _ = evaluate_answer(db_session, q.id, "A")
    assert is_correct
    assert attempt3.consecutive_correct == 2
    assert attempt3.needs_review is False

def test_set_completion_scoring_and_weak_subtopics(db_session):
    qs = QuizSet(topic_id="variables-and-types", set_number=1, total_questions=2)
    db_session.add(qs)
    db_session.flush()

    q1 = QuizQuestion(set_id=qs.id, topic_id=qs.topic_id, question_index=1, question_type="mcq", prompt="Q1", correct_answer="A", explanation="", subtopic="primitives")
    q2 = QuizQuestion(set_id=qs.id, topic_id=qs.topic_id, question_index=2, question_type="mcq", prompt="Q2", correct_answer="B", explanation="", subtopic="references")
    db_session.add_all([q1, q2])
    db_session.commit()

    # Answer Q1 correct, Q2 wrong
    evaluate_answer(db_session, q1.id, "A")
    evaluate_answer(db_session, q2.id, "C")

    # Verify score = 50%, not passed (< 70%), weak subtopics contains "references"
    db_session.refresh(qs)
    assert qs.completed is True
    assert qs.score == 50.0
    assert qs.passed is False
    assert "references" in qs.weak_subtopics

def test_unlock_next_topic_rule(db_session):
    # Rule: Next topic unlocks when current topic reaches at least "Reviewing"
    prog1 = db_session.query(TopicProgress).filter(TopicProgress.topic_id == "variables-and-types").first()
    prog2 = db_session.query(TopicProgress).filter(TopicProgress.topic_id == "operators").first()

    assert not prog2.unlocked

    # If status is Learning, next topic remains locked
    prog1.status = "Learning"
    db_session.commit()
    check_and_unlock_next_topic(db_session, "variables-and-types")
    db_session.refresh(prog2)
    assert not prog2.unlocked

    # When status is promoted to Reviewing, next topic unlocks
    prog1.status = "Reviewing"
    db_session.commit()
    check_and_unlock_next_topic(db_session, "variables-and-types")
    db_session.refresh(prog2)
    assert prog2.unlocked is True
    assert prog2.status == "Learning"

def test_mastery_evaluation_rules(db_session):
    prog = db_session.query(TopicProgress).filter(TopicProgress.topic_id == "variables-and-types").first()

    # Case 1: Set passed (75%), teach-back passed (80%), app challenge passed (80%) -> Promoted to "Reviewing"
    prog.highest_score = 75.0
    prog.latest_score = 75.0
    prog.teach_back_passed = True
    prog.teach_back_score = 80.0
    prog.app_challenge_passed = True
    prog.app_challenge_score = 80.0
    db_session.commit()

    status = evaluate_topic_mastery(db_session, "variables-and-types")
    assert status == "Reviewing"

    # Case 2: All scores >= 85, but retention quizzes not yet finished -> remains "Reviewing"
    prog.highest_score = 90.0
    prog.teach_back_score = 90.0
    prog.app_challenge_score = 90.0
    db_session.commit()

    status = evaluate_topic_mastery(db_session, "variables-and-types")
    assert status == "Reviewing"

    # Case 3: Complete all 3 retention stages with >= 85 -> Promoted to "Mastered"
    prog.retention_stage = 3
    rq1 = RetentionQuiz(topic_id=prog.topic_id, stage=1, due_at=utc_now(), completed_at=utc_now(), score=90.0, passed=True)
    rq2 = RetentionQuiz(topic_id=prog.topic_id, stage=2, due_at=utc_now(), completed_at=utc_now(), score=88.0, passed=True)
    rq3 = RetentionQuiz(topic_id=prog.topic_id, stage=3, due_at=utc_now(), completed_at=utc_now(), score=95.0, passed=True)
    db_session.add_all([rq1, rq2, rq3])
    db_session.commit()

    status = evaluate_topic_mastery(db_session, "variables-and-types")
    assert status == "Mastered"

