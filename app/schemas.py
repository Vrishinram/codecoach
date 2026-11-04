from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

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

