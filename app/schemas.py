import re
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator

TIME_24H_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# --- Curriculum & Links ---
class LinkItem(BaseModel):
    id: Optional[int] = None
    topic_id: str
    title: str
    url: str
    type: str = "article"
    level: str = "beginner"
    description: Optional[str] = None
    is_active: bool = True
    is_custom: bool = False
    is_completed: bool = False

class LinkCreate(BaseModel):
    topic_id: str
    title: str
    url: str
    type: str = "article"
    level: str = "beginner"
    description: Optional[str] = None

class TopicSummary(BaseModel):
    id: str
    level_id: str
    title: str
    order: int
    description: Optional[str] = None
    subtopics: List[str] = []
    status: str = "New" # "New", "Learning", "Reviewing", "Mastered"
    unlocked: bool = False
    sets_completed: int = 0
    highest_score: float = 0.0
    latest_score: float = 0.0
    teach_back_passed: bool = False
    app_challenge_passed: bool = False
    retention_stage: int = 0
    next_retention_due_at: Optional[str] = None

class LevelSummary(BaseModel):
    id: str
    title: str
    order: int
    description: Optional[str] = None
    topics: List[TopicSummary] = []

# --- Quiz & Sets ---
class QuestionDTO(BaseModel):
    id: int
    set_id: int
    topic_id: str
    question_index: int
    question_type: str # "mcq", "output_prediction", "fill_blank", "coding"
    prompt: str
    code_snippet: Optional[str] = None
    options: List[str] = []
    hint: Optional[str] = None
    difficulty: int = 1
    subtopic: Optional[str] = None

class AnswerSubmission(BaseModel):
    question_id: int
    user_answer: str
    response_time_ms: Optional[int] = 0

class AnswerResult(BaseModel):
    question_id: int
    is_correct: bool
    correct_answer: str
    explanation: str
    consecutive_correct: int
    needs_review: bool

class QuizSetStatus(BaseModel):
    id: int
    topic_id: str
    set_number: int
    total_questions: int
    answered_count: int
    correct_count: int
    score: float
    completed: bool
    passed: bool
    weak_subtopics: List[str] = []
    feedback: Optional[str] = None

class LearningReport(BaseModel):
    topic_id: str
    topic_title: str
    set_number: int
    score: float
    passed: bool
    pass_threshold: int
    mastery_threshold: int
    status: str
    strengths: List[str]
    weak_spots: List[str]
    teach_back_status: str
    app_challenge_status: str
    retention_status: str
    recommended_action: str
    start_links: List[LinkItem] = []
    end_links: List[LinkItem] = []

# --- Verification ---
class TeachBackSubmit(BaseModel):
    topic_id: str
    student_explanation: str

class TeachBackRubricResult(BaseModel):
    accuracy_score: float
    completeness_score: float
    clarity_score: float
    overall_score: float
    passed: bool
    feedback: str
    missing_points: List[str] = []

class AppChallengeRequest(BaseModel):
    topic_id: str

class AppChallengePrompt(BaseModel):
    topic_id: str
    prompt: str
    starter_code: Optional[str] = None

class AppChallengeSubmit(BaseModel):
    topic_id: str
    student_code: str

class AppChallengeReviewResult(BaseModel):
    score: float
    passed: bool
    correctness_notes: str
    edge_case_notes: str
    style_notes: str
    feedback: str

# --- Retention & Reviews ---
class RetentionQuizDTO(BaseModel):
    id: int
    topic_id: str
    topic_title: str
    stage: int
    due_at: str
    questions: List[QuestionDTO]

# --- Push & Settings ---
class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    user_agent: Optional[str] = None

class SettingsUpdate(BaseModel):
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    ntfy_enabled: Optional[bool] = None
    reminders_paused: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    reminder_times: Optional[str] = None
    user_email: Optional[str] = None
    ntfy_topic: Optional[str] = None

    @field_validator("reminder_times")
    @classmethod
    def validate_reminder_times(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if not parts:
            raise ValueError("Add at least one reminder time (HH:MM).")
        for p in parts:
            if not TIME_24H_REGEX.match(p):
                raise ValueError(f"Invalid time '{p}'. Use 24h HH:MM format (e.g. 08:00).")
        return ",".join(parts)

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_quiet_hours(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        val = v.strip()
        if not TIME_24H_REGEX.match(val):
            raise ValueError(f"Quiet hour must be in 24h HH:MM format (00:00 to 23:59), got '{v}'.")
        return val

    @field_validator("user_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        val = v.strip()
        if val and ("@" not in val or "." not in val.split("@")[-1]):
            raise ValueError("Invalid email format.")
        return val

class DashboardStats(BaseModel):
    assistant_name: str
    topics_total: int
    topics_mastered: int
    topics_reviewing: int
    topics_learning: int
    current_streak: int
    longest_streak: int
    due_reviews_count: int
    total_tokens_used: int
    token_usage_by_model: Dict[str, int] = {}
    score_history: List[Dict[str, Any]] = []
    levels: List[LevelSummary] = []
    due_retention_quizzes: List[Dict[str, Any]] = []

# --- Placement Test ---
class PlacementQuestion(BaseModel):
    id: int
    topic_id: str
    level_id: str
    prompt: str
    code_snippet: Optional[str] = None
    options: List[str]
    correct_option_index: int

class PlacementAnswer(BaseModel):
    question_id: int
    selected_option_index: int

class PlacementSubmit(BaseModel):
    answers: List[PlacementAnswer]

class PlacementResult(BaseModel):
    score: float
    recommended_topic_id: str
    recommended_topic_title: str
    unlocked_topics: List[str]
    message: str

# --- Phase 1: Practice Features Schemas ---
class CodeExecutionRequest(BaseModel):
    code: str
    stdin: Optional[str] = ""
    timeout_seconds: Optional[int] = 5

class CodeExecutionResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    engine: str # "piston", "judge0", "llm_simulated"
    is_simulated: bool = False
    warning: Optional[str] = None

class ChallengeTestCase(BaseModel):
    input: str
    expected_output: str
    is_hidden: bool = False

class CodingChallengeDTO(BaseModel):
    id: str
    title: str
    difficulty: str
    topic_id: str
    description: str
    starter_code: str
    public_test_cases: List[Dict[str, Any]] = []

class ChallengeTestResult(BaseModel):
    test_index: int
    input: str
    expected_output: str
    actual_output: str
    passed: bool
    is_hidden: bool = False
    error: Optional[str] = None

class ChallengeSubmitRequest(BaseModel):
    code: str

class ChallengeSubmitResponse(BaseModel):
    challenge_id: str
    passed: bool
    tests_passed: int
    tests_total: int
    test_results: List[ChallengeTestResult]
    execution_engine: str
    is_simulated: bool
    feedback: str

class BugHuntScenarioDTO(BaseModel):
    id: str
    title: str
    difficulty: str
    topic_id: str
    description: str
    code_snippet: str
    total_bugs: int

class BugHuntSubmitRequest(BaseModel):
    selected_lines: List[int] # 1-based line numbers

class BugDetail(BaseModel):
    line: int
    bug_type: str
    explanation: str
    fix_code: str

class BugHuntSubmitResponse(BaseModel):
    scenario_id: str
    score: float
    found_count: int
    total_bugs: int
    all_found: bool
    feedback: str
    detected_bugs: List[BugDetail] = []
    missed_lines: List[int] = []
    false_positives: List[int] = []

class CompilerDecodeRequest(BaseModel):
    error_text: str

class CompilerDecodeResponse(BaseModel):
    error_code: Optional[str] = None
    error_title: str
    plain_explanation: str
    likely_causes: List[str]
    recommended_fix: str
    code_example_before: Optional[str] = None
    code_example_after: Optional[str] = None
    related_topic_id: Optional[str] = None
    related_topic_title: Optional[str] = None
    is_ai_fallback: bool = False

class RefactorScenarioDTO(BaseModel):
    id: str
    title: str
    topic_id: str
    description: str
    bad_code: str

class RefactorSubmitRequest(BaseModel):
    refactored_code: str

class RefactorGradeResponse(BaseModel):
    score: float
    passed: bool
    readability_score: float
    idiom_score: float
    correctness_score: float
    performance_score: float
    feedback: str
    strengths: List[str]
    improvements: List[str]
    ideal_comparison: str

class OutputPredictorQuestion(BaseModel):
    id: str
    topic_id: str
    title: str
    code_snippet: str
    options: List[str]

class OutputPredictorRoundResponse(BaseModel):
    round_id: str
    time_limit_seconds: int = 60
    questions: List[OutputPredictorQuestion]

class OutputPredictorAnswer(BaseModel):
    question_id: str
    selected_option: str
    time_spent_seconds: float

class OutputPredictorSubmitRequest(BaseModel):
    round_id: str
    answers: List[OutputPredictorAnswer]

class OutputPredictorResultItem(BaseModel):
    question_id: str
    user_answer: str
    correct_output: str
    is_correct: bool
    explanation: str

class OutputPredictorSubmitResponse(BaseModel):
    total_score: int
    correct_count: int
    total_questions: int
    max_streak: int
    streak_bonus: int
    speed_bonus: int
    results: List[OutputPredictorResultItem]

# --- Phase 2: Smart Learning Schemas ---

class SubtopicAdaptiveMetric(BaseModel):
    subtopic: str
    total_attempts: int
    correct_attempts: int
    accuracy_pct: float
    avg_response_time_ms: int
    recommended_difficulty: int
    difficulty_label: str
    readiness_status: str

class AdaptiveMetricsResponse(BaseModel):
    topic_id: Optional[str] = None
    overall_recommended_difficulty: int
    subtopics: List[SubtopicAdaptiveMetric]

class WeakSpotSummary(BaseModel):
    subtopic: str
    topic_id: str
    topic_title: str
    miss_count: int
    accuracy_pct: float

class WeakSpotDrillResponse(BaseModel):
    set_id: int
    total_questions: int
    targeted_subtopics: List[str]
    message: str

class ExplainDifferentlyRequest(BaseModel):
    concept: str
    current_explanation: str
    perspective: str # "analogy", "simplified", "code_first"
    context_code: Optional[str] = None

class ExplainDifferentlyResponse(BaseModel):
    concept: str
    perspective: str
    explanation: str
    is_cached: bool = False

class ConceptMapNode(BaseModel):
    id: str
    level_id: str
    level_title: str
    title: str
    order: int
    status: str
    mastery_score: float
    subtopics: List[str]
    unlocked: bool
    prerequisites: List[str]

class ConceptMapEdge(BaseModel):
    source: str
    target: str
    relationship_type: str = "prerequisite"

class ConceptMapResponse(BaseModel):
    nodes: List[ConceptMapNode]
    edges: List[ConceptMapEdge]
    total_nodes: int
    mastered_nodes: int
    learning_nodes: int
    locked_nodes: int

class PersonalNoteCreate(BaseModel):
    title: str
    content: str
    topic_id: Optional[str] = None
    tags: List[str] = []

class PersonalNoteResponse(BaseModel):
    id: int
    title: str
    content: str
    topic_id: Optional[str] = None
    tags: List[str] = []
    created_at: str
    updated_at: str

class FlashcardResponse(BaseModel):
    id: int
    note_id: Optional[int] = None
    topic_id: Optional[str] = None
    subtopic: Optional[str] = None
    front: str
    back: str
    code_snippet: Optional[str] = None
    source_type: str
    interval_days: int
    ease_factor: float
    repetitions: int
    due_date: str
    is_due: bool

class FlashcardReviewRequest(BaseModel):
    rating: int # 1: Again, 2: Hard, 3: Good, 4: Easy

class FlashcardReviewResponse(BaseModel):
    id: int
    rating: int
    new_interval_days: int
    new_ease_factor: float
    repetitions: int
    next_due_date: str

class FlashcardGenerateFromMissedResponse(BaseModel):
    generated_count: int
    flashcards: List[FlashcardResponse]

class StudyPlanCreate(BaseModel):
    goal_title: str
    target_role: str = "Junior .NET Developer"
    duration_weeks: int = 8
    daily_minutes: int = 30

class StudyPlanWeek(BaseModel):
    week_number: int
    title: str
    topic_ids: List[str]
    topic_titles: List[str]
    goal_description: str
    completed: bool
    progress_pct: float

class StudyPlanResponse(BaseModel):
    id: int
    goal_title: str
    target_role: str
    duration_weeks: int
    daily_minutes: int
    start_date: str
    target_date: Optional[str] = None
    current_week: int
    is_active: bool
    weeks: List[StudyPlanWeek]
    overall_progress_pct: float



