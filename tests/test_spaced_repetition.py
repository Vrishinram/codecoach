import pytest
from datetime import timedelta
from app.models import RetentionQuiz, TopicProgress, utc_now
from app.services.verification_service import schedule_initial_retention_if_eligible, advance_retention_stage

def test_spaced_repetition_progression(db_session):
    topic_id = "variables-and-types"
    prog = db_session.query(TopicProgress).filter(TopicProgress.topic_id == topic_id).first()

    # 1. Schedule initial stage 1 check
    schedule_initial_retention_if_eligible(db_session, topic_id)
    rq1 = db_session.query(RetentionQuiz).filter(RetentionQuiz.topic_id == topic_id, RetentionQuiz.stage == 1).first()
    assert rq1 is not None
    assert rq1.stage == 1
    assert prog.next_retention_due_at is not None

    # 2. Advance stage 1 with score 85 -> schedules stage 2 (3 days later)
    advance_retention_stage(db_session, rq1.id, score=85.0)
    db_session.refresh(prog)
    assert prog.retention_stage == 1

    rq2 = db_session.query(RetentionQuiz).filter(RetentionQuiz.topic_id == topic_id, RetentionQuiz.stage == 2).first()
    assert rq2 is not None
    assert rq2.stage == 2
    # Verify due_at is approximately 3 days in future
    diff_days = (rq2.due_at - utc_now()).days
    assert 2 <= diff_days <= 3

    # 3. Advance stage 2 with score 90 -> schedules stage 3 (7 days later)
    advance_retention_stage(db_session, rq2.id, score=90.0)
    db_session.refresh(prog)
    assert prog.retention_stage == 2

    rq3 = db_session.query(RetentionQuiz).filter(RetentionQuiz.topic_id == topic_id, RetentionQuiz.stage == 3).first()
    assert rq3 is not None
    assert rq3.stage == 3
    diff_days_3 = (rq3.due_at - utc_now()).days
    assert 6 <= diff_days_3 <= 7

    # 4. Advance stage 3 with score 92 -> all retention stages completed!
    advance_retention_stage(db_session, rq3.id, score=92.0)
    db_session.refresh(prog)
    assert prog.retention_stage == 3
    assert prog.next_retention_due_at is None

