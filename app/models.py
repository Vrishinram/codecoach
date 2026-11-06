import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class CurriculumLevel(Base):
    __tablename__ = "curriculum_levels"

    id = Column(String(50), primary_key=True)
    title = Column(String(100), nullable=False)
    order = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)

    topics = relationship("CurriculumTopic", back_populates="level", cascade="all, delete-orphan", order_by="CurriculumTopic.order")

class CurriculumTopic(Base):
    __tablename__ = "curriculum_topics"

    id = Column(String(80), primary_key=True)
    level_id = Column(String(50), ForeignKey("curriculum_levels.id"), nullable=False)
    title = Column(String(120), nullable=False)
    order = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    subtopics_json = Column(Text, default="[]")  # List[str] in JSON

    level = relationship("CurriculumLevel", back_populates="topics")
    links = relationship("LearningLink", back_populates="topic", cascade="all, delete-orphan")
    progress = relationship("TopicProgress", back_populates="topic", uselist=False, cascade="all, delete-orphan")
    quiz_sets = relationship("QuizSet", back_populates="topic", cascade="all, delete-orphan")

    @property
    def subtopics(self):
        try:
            return json.loads(self.subtopics_json or "[]")
        except Exception:
            return []

class LearningLink(Base):
    __tablename__ = "learning_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(80), ForeignKey("curriculum_topics.id"), nullable=False)
    title = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    type = Column(String(20), default="article")  # "article" or "video"
    level = Column(String(20), default="beginner") # beginner, intermediate, advanced
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)  # verified via HTTP check
    is_custom = Column(Boolean, default=False)  # added by user
    is_completed = Column(Boolean, default=False) # marked watched / read
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    topic = relationship("CurriculumTopic", back_populates="links")

class TopicProgress(Base):
    __tablename__ = "topic_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(80), ForeignKey("curriculum_topics.id"), unique=True, nullable=False)
    
    # Status: "New", "Learning", "Reviewing", "Mastered"
    status = Column(String(20), default="New", nullable=False)
    
    current_set_number = Column(Integer, default=1)
    sets_completed = Column(Integer, default=0)
    highest_score = Column(Float, default=0.0)
    latest_score = Column(Float, default=0.0)
    
    # Verification checks
    teach_back_passed = Column(Boolean, default=False)
    teach_back_score = Column(Float, default=0.0)
    
    app_challenge_passed = Column(Boolean, default=False)
    app_challenge_score = Column(Float, default=0.0)
    
    # Retention Spaced Repetition (0: none, 1: 1-day, 2: 3-day, 3: 7-day)
    retention_stage = Column(Integer, default=0)
    next_retention_due_at = Column(DateTime, nullable=True)
    
    unlocked = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    topic = relationship("CurriculumTopic", back_populates="progress")

class QuizSet(Base):
    __tablename__ = "quiz_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(80), ForeignKey("curriculum_topics.id"), nullable=False)
    set_number = Column(Integer, default=1)
    is_retry_set = Column(Boolean, default=False)
    total_questions = Column(Integer, default=25)
    score = Column(Float, default=0.0)
    passed = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    weak_subtopics_json = Column(Text, default="[]")
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    topic = relationship("CurriculumTopic", back_populates="quiz_sets")
    questions = relationship("QuizQuestion", back_populates="quiz_set", cascade="all, delete-orphan", order_by="QuizQuestion.question_index")

    @property
    def weak_subtopics(self):
        try:
            return json.loads(self.weak_subtopics_json or "[]")
        except Exception:
            return []

class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    set_id = Column(Integer, ForeignKey("quiz_sets.id"), nullable=False)
    topic_id = Column(String(80), nullable=False)
    question_index = Column(Integer, nullable=False)
    
    # "mcq", "output_prediction", "fill_blank", "coding"
    question_type = Column(String(30), nullable=False)
    prompt = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    options_json = Column(Text, default="[]")  # For MCQ: ["A) ...", "B) ..."]
    correct_answer = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    hint = Column(Text, nullable=True)
    difficulty = Column(Integer, default=1) # 1 to 5
    subtopic = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=utc_now)

    quiz_set = relationship("QuizSet", back_populates="questions")
    attempts = relationship("QuestionAttempt", back_populates="question", cascade="all, delete-orphan")

    @property
    def options(self):
        try:
            return json.loads(self.options_json or "[]")
        except Exception:
            return []

class QuestionAttempt(Base):
    __tablename__ = "question_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("quiz_questions.id"), nullable=False)
    topic_id = Column(String(80), nullable=False)
    user_answer = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    consecutive_correct = Column(Integer, default=0) # Must reach 2 to be retired from review
    needs_review = Column(Boolean, default=False)
    response_time_ms = Column(Integer, default=0)
    attempted_at = Column(DateTime, default=utc_now)

    question = relationship("QuizQuestion", back_populates="attempts")

class TeachBackSubmission(Base):
    __tablename__ = "teach_back_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(80), ForeignKey("curriculum_topics.id"), nullable=False)
    student_explanation = Column(Text, nullable=False)
    accuracy_score = Column(Float, default=0.0)
    completeness_score = Column(Float, default=0.0)
    clarity_score = Column(Float, default=0.0)
    overall_score = Column(Float, default=0.0)
    missing_points_json = Column(Text, default="[]")
    feedback = Column(Text, nullable=False)
    passed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    @property
    def missing_points(self):
        try:
            return json.loads(self.missing_points_json or "[]")
        except Exception:
            return []

class ApplicationChallengeSubmission(Base):
    __tablename__ = "application_challenge_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(80), ForeignKey("curriculum_topics.id"), nullable=False)
    prompt = Column(Text, nullable=False)
    student_code = Column(Text, nullable=False)
    score = Column(Float, default=0.0)
    correctness_notes = Column(Text, nullable=True)
    edge_case_notes = Column(Text, nullable=True)
    style_notes = Column(Text, nullable=True)
    feedback = Column(Text, nullable=False)
    passed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

class RetentionQuiz(Base):
    __tablename__ = "retention_quizzes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String(80), ForeignKey("curriculum_topics.id"), nullable=False)
    stage = Column(Integer, nullable=False) # 1 (1-day), 2 (3-day), 3 (7-day)
    due_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    score = Column(Float, default=0.0)
    passed = Column(Boolean, default=False)
    questions_json = Column(Text, default="[]") # 5 review questions
    created_at = Column(DateTime, default=utc_now)

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(Text, unique=True, nullable=False)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String(20), nullable=False) # "push", "email", "ntfy"
    notification_type = Column(String(50), nullable=False) # "daily_reminder", "weekly_summary", "comeback_nudge", "celebration", "test"
    subject = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    status = Column(String(20), nullable=False) # "sent", "failed"
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=utc_now)

class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    operation = Column(String(50), default="chat") # "chat", "generate_quiz", "grade_teach_back", "grade_app_challenge", "placement"
    created_at = Column(DateTime, default=utc_now)

class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_active_date = Column(String(10), nullable=True) # "YYYY-MM-DD"
    placement_completed = Column(Boolean, default=False)
    placement_score = Column(Float, default=0.0)
    
    # Settings toggles
    push_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)
    ntfy_enabled = Column(Boolean, default=True)
    reminders_paused = Column(Boolean, default=False)
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String(5), default="22:00")
    quiet_hours_end = Column(String(5), default="07:00")
    reminder_times = Column(String(50), default="08:00,20:00")
    custom_email = Column(String(120), nullable=True)
    custom_ntfy_topic = Column(String(120), nullable=True)

    # Google OAuth 2.0 & Gmail API
    google_connected = Column(Boolean, default=False)
    google_email = Column(String(120), nullable=True)
    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_token_expiry = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

# ============================================================================
# PHASE 1: PRACTICE FEATURES MODELS
# ============================================================================

class PlaygroundSnippet(Base):
    __tablename__ = "playground_snippets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_session_id = Column(String(100), nullable=True)
    title = Column(String(150), nullable=False, default="Untitled C# Snippet")
    code = Column(Text, nullable=False)
    csharp_version = Column(String(20), default="13.0")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

class CodingChallenge(Base):
    __tablename__ = "coding_challenges"

    id = Column(String(80), primary_key=True)
    title = Column(String(150), nullable=False)
    difficulty = Column(String(20), default="Beginner")
    topic_id = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    starter_code = Column(Text, nullable=False)
    test_cases_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utc_now)

    @property
    def test_cases(self):
        try:
            return json.loads(self.test_cases_json or "[]")
        except Exception:
            return []

class ChallengeSubmission(Base):
    __tablename__ = "challenge_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    challenge_id = Column(String(80), nullable=False)
    user_session_id = Column(String(100), nullable=True)
    code = Column(Text, nullable=False)
    passed = Column(Boolean, default=False)
    tests_passed = Column(Integer, default=0)
    tests_total = Column(Integer, default=0)
    execution_engine = Column(String(30), default="piston")
    is_simulated = Column(Boolean, default=False)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

class BugHuntScenario(Base):
    __tablename__ = "bug_hunt_scenarios"

    id = Column(String(80), primary_key=True)
    title = Column(String(150), nullable=False)
    difficulty = Column(String(20), default="Beginner")
    topic_id = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=False)
    buggy_lines_json = Column(Text, default="[]") # List[int]
    explanations_json = Column(Text, default="{}") # Dict[str, Dict]
    created_at = Column(DateTime, default=utc_now)

    @property
    def buggy_lines(self):
        try:
            return json.loads(self.buggy_lines_json or "[]")
        except Exception:
            return []

    @property
    def explanations(self):
        try:
            return json.loads(self.explanations_json or "{}")
        except Exception:
            return {}

class RefactorScenario(Base):
    __tablename__ = "refactor_scenarios"

    id = Column(String(80), primary_key=True)
    title = Column(String(150), nullable=False)
    topic_id = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    bad_code = Column(Text, nullable=False)
    ideal_refactor = Column(Text, nullable=False)
    rubric_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utc_now)

    @property
    def rubric(self):
        try:
            return json.loads(self.rubric_json or "{}")
        except Exception:
            return {}

class OutputPredictorScenario(Base):
    __tablename__ = "output_predictor_scenarios"

    id = Column(String(80), primary_key=True)
    topic_id = Column(String(80), nullable=False)
    title = Column(String(150), nullable=False)
    code_snippet = Column(Text, nullable=False)
    options_json = Column(Text, default="[]")
    correct_output = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    difficulty = Column(Integer, default=1)
    created_at = Column(DateTime, default=utc_now)

    @property
    def options(self):
        try:
            return json.loads(self.options_json or "[]")
        except Exception:
            return []

# ============================================================================
# PHASE 2: SMART LEARNING MODELS
# ============================================================================

class PersonalNote(Base):
    __tablename__ = "personal_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_session_id = Column(String(100), nullable=True)
    topic_id = Column(String(80), nullable=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    tags_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    flashcards = relationship("Flashcard", back_populates="note", cascade="all, delete-orphan")

    @property
    def tags(self):
        try:
            return json.loads(self.tags_json or "[]")
        except Exception:
            return []

class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_session_id = Column(String(100), nullable=True)
    note_id = Column(Integer, ForeignKey("personal_notes.id", ondelete="SET NULL"), nullable=True)
    topic_id = Column(String(80), nullable=True)
    subtopic = Column(String(120), nullable=True)
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    source_type = Column(String(30), default="manual")  # "manual", "note", "missed_question"
    
    # SM-2 Spaced Repetition Parameters
    interval_days = Column(Integer, default=1)
    ease_factor = Column(Float, default=2.5)
    repetitions = Column(Integer, default=0)
    due_date = Column(DateTime, default=utc_now)
    last_reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    note = relationship("PersonalNote", back_populates="flashcards")

class StudyPlan(Base):
    __tablename__ = "study_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_session_id = Column(String(100), nullable=True)
    goal_title = Column(String(200), nullable=False)
    target_role = Column(String(100), nullable=False, default="Junior .NET Developer")
    duration_weeks = Column(Integer, default=8)
    daily_minutes = Column(Integer, default=30)
    start_date = Column(DateTime, default=utc_now)
    target_date = Column(DateTime, nullable=True)
    weeks_json = Column(Text, default="[]")
    current_week = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    @property
    def weeks(self):
        try:
            return json.loads(self.weeks_json or "[]")
        except Exception:
            return []

class ExplanationCache(Base):
    __tablename__ = "explanation_caches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(128), unique=True, index=True, nullable=False)
    concept = Column(String(255), nullable=False)
    perspective = Column(String(30), nullable=False)  # "analogy", "simplified", "code_first"
    explanation = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)


