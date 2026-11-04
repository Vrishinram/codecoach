import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    CurriculumTopic, QuizSet, QuizQuestion, QuestionAttempt,
    TopicProgress, RetentionQuiz, UserProfile, CurriculumLevel, utc_now
)
from app.schemas import (
    QuestionDTO, AnswerSubmission, AnswerResult, QuizSetStatus,
    LearningReport, TeachBackSubmit, TeachBackRubricResult,
    AppChallengePrompt, AppChallengeSubmit, AppChallengeReviewResult,
    PlacementSubmit, PlacementResult, RetentionQuizDTO
)
from app.services.quiz_service import (
    get_or_create_active_set, get_next_unanswered_question,
    evaluate_answer, get_due_review_questions
)
from app.services.verification_service import (
    submit_teach_back, get_or_create_app_challenge,
    submit_app_challenge, generate_learning_report,
    advance_retention_stage
)
from app.services.curriculum_service import check_and_unlock_next_topic, update_user_activity_streak

router = APIRouter(prefix="/api", tags=["Quiz & Verification"])
logger = logging.getLogger("codecoach.api.quiz")

def _to_question_dto(q: QuizQuestion) -> QuestionDTO:
    return QuestionDTO(
        id=q.id,
        set_id=q.set_id,
        topic_id=q.topic_id,
        question_index=q.question_index,
        question_type=q.question_type,
        prompt=q.prompt,
        code_snippet=q.code_snippet,
        options=q.options,
        hint=q.hint,
        difficulty=q.difficulty,
        subtopic=q.subtopic
    )

@router.post("/quiz/start/{topic_id}")
async def start_quiz_set(topic_id: str, db: Session = Depends(get_db)):
    """
    Starts or resumes a set of SET_SIZE questions for the given topic.
    """
    topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    quiz_set = await get_or_create_active_set(db, topic_id)
    next_q = get_next_unanswered_question(db, quiz_set.id)

    answered_count = len(quiz_set.questions) - (
        len(quiz_set.questions) if not next_q else (len(quiz_set.questions) - next_q.question_index + 1)
    )

    return {
        "set_id": quiz_set.id,
        "topic_id": topic_id,
        "topic_title": topic.title,
        "set_number": quiz_set.set_number,
        "total_questions": len(quiz_set.questions),
        "current_question": _to_question_dto(next_q) if next_q else None,
        "is_completed": quiz_set.completed
    }

@router.get("/quiz/current/{topic_id}")
async def get_current_question(topic_id: str, db: Session = Depends(get_db)):
    """
    Gets the current active question for this topic's set.
    """
    quiz_set = db.query(QuizSet).filter(
        QuizSet.topic_id == topic_id,
        QuizSet.completed == False
    ).order_by(QuizSet.id.desc()).first()

    if not quiz_set:
        # Check if latest set is completed
        latest = db.query(QuizSet).filter(QuizSet.topic_id == topic_id).order_by(QuizSet.id.desc()).first()
        if latest and latest.completed:
            return {"set_id": latest.id, "is_completed": True, "current_question": None}
        return {"set_id": None, "is_completed": False, "current_question": None}

    next_q = get_next_unanswered_question(db, quiz_set.id)
    return {
        "set_id": quiz_set.id,
        "is_completed": next_q is None,
        "current_question": _to_question_dto(next_q) if next_q else None
    }

@router.post("/quiz/submit-answer", response_model=AnswerResult)
async def submit_question_answer(payload: AnswerSubmission, db: Session = Depends(get_db)):
    """
    Submits user answer to a question and returns immediate evaluation + explanation.
    """
    is_correct, attempt, question = evaluate_answer(db, payload.question_id, payload.user_answer)
    return AnswerResult(
        question_id=question.id,
        is_correct=is_correct,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
        consecutive_correct=attempt.consecutive_correct,
        needs_review=attempt.needs_review
    )

@router.get("/quiz/report/{set_id}", response_model=LearningReport)
async def get_quiz_learning_report(set_id: int, db: Session = Depends(get_db)):
    """
    Returns the post-set Learning Report.
    """
    return generate_learning_report(db, set_id)

@router.post("/quiz/retry/{topic_id}")
async def retry_failed_set(topic_id: str, db: Session = Depends(get_db)):
    """
    Creates a new retry set focused on the subtopics the user got wrong.
    """
    latest_set = db.query(QuizSet).filter(
        QuizSet.topic_id == topic_id
    ).order_by(QuizSet.id.desc()).first()

    weak = latest_set.weak_subtopics if latest_set else []
    new_set = await get_or_create_active_set(db, topic_id, is_retry=True, weak_subtopics=weak)
    first_q = get_next_unanswered_question(db, new_set.id)

    return {
        "set_id": new_set.id,
        "topic_id": topic_id,
        "message": f"Retry set #{new_set.set_number} generated focusing on {', '.join(weak) if weak else 'reinforcement'}.",
        "first_question": _to_question_dto(first_q) if first_q else None
    }

@router.post("/verification/teach-back", response_model=TeachBackRubricResult)
async def verify_teach_back(payload: TeachBackSubmit, db: Session = Depends(get_db)):
    """
    Step 2 of Learning Verification: Evaluates student's teach-back explanation.
    """
    submission = await submit_teach_back(db, payload.topic_id, payload.student_explanation)
    return TeachBackRubricResult(
        accuracy_score=submission.accuracy_score,
        completeness_score=submission.completeness_score,
        clarity_score=submission.clarity_score,
        overall_score=submission.overall_score,
        passed=submission.passed,
        feedback=submission.feedback,
        missing_points=submission.missing_points
    )

@router.get("/verification/app-challenge/{topic_id}", response_model=AppChallengePrompt)
async def get_app_challenge(topic_id: str, db: Session = Depends(get_db)):
    """
    Step 3 of Learning Verification: Gets a practical C# coding challenge.
    """
    challenge = await get_or_create_app_challenge(db, topic_id)
    return AppChallengePrompt(
        topic_id=topic_id,
        prompt=challenge["prompt"],
        starter_code=challenge.get("starter_code")
    )

@router.post("/verification/app-challenge/submit", response_model=AppChallengeReviewResult)
async def review_student_app_challenge(payload: AppChallengeSubmit, db: Session = Depends(get_db)):
    """
    Reviews practical coding challenge submission.
    """
    # Fetch prompt
    challenge = await get_or_create_app_challenge(db, payload.topic_id)
    submission = await submit_app_challenge(
        db,
        topic_id=payload.topic_id,
        problem_prompt=challenge["prompt"],
        student_code=payload.student_code
    )
    return AppChallengeReviewResult(
        score=submission.score,
        passed=submission.passed,
        correctness_notes=submission.correctness_notes or "",
        edge_case_notes=submission.edge_case_notes or "",
        style_notes=submission.style_notes or "",
        feedback=submission.feedback
    )

@router.get("/retention/due")
async def get_due_retention_quizzes(db: Session = Depends(get_db)):
    """
    Step 4: Returns due spaced repetition quizzes (1d, 3d, 7d).
    """
    now = utc_now()
    due = db.query(RetentionQuiz).filter(
        RetentionQuiz.due_at <= now,
        RetentionQuiz.completed_at == None
    ).all()

    result = []
    for r in due:
        topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == r.topic_id).first()
        # Fetch up to 5 review questions for this topic
        review_qs = db.query(QuizQuestion).filter(QuizQuestion.topic_id == r.topic_id).limit(5).all()
        result.append({
            "id": r.id,
            "topic_id": r.topic_id,
            "topic_title": topic.title if topic else r.topic_id,
            "stage": r.stage,
            "due_at": r.due_at.isoformat(),
            "questions": [_to_question_dto(q) for q in review_qs]
        })
    return result

@router.post("/retention/submit/{retention_id}")
async def submit_retention_quiz(retention_id: int, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Submits score for a retention quiz and advances stage.
    """
    score = float(payload.get("score", 0.0))
    rq = advance_retention_stage(db, retention_id, score)
    return {
        "id": rq.id,
        "stage": rq.stage,
        "score": rq.score,
        "passed": rq.passed,
        "message": "Retention quiz recorded successfully!"
    }

@router.get("/placement/questions")
async def get_placement_questions():
    """
    Curated 10-question placement test across all 6 curriculum levels.
    """
    questions = [
        {
            "id": 1,
            "topic_id": "variables-and-types",
            "level_id": "csharp-basics",
            "prompt": "What is the difference between a value type and a reference type in C#?",
            "code_snippet": None,
            "options": [
                "A) Value types are stored on the stack (unless boxed) and contain data directly; reference types store references to objects on the managed heap.",
                "B) Value types can never be null under any circumstances, even with Nullable<T>.",
                "C) Reference types cannot contain methods or constructors.",
                "D) Value types are always passed by reference automatically."
            ],
            "correct_option_index": 0
        },
        {
            "id": 2,
            "topic_id": "operators-and-expressions",
            "level_id": "csharp-basics",
            "prompt": "What does the null-coalescing assignment operator `??=` do in C#?",
            "code_snippet": "string name = null;\nname ??= \"Default\";",
            "options": [
                "A) It throws an ArgumentNullException if the left operand is null.",
                "B) It assigns the right-hand operand to the left-hand operand only if the left-hand operand evaluates to null.",
                "C) It concatenates the two strings if neither is null.",
                "D) It performs a deep equality comparison."
            ],
            "correct_option_index": 1
        },
        {
            "id": 3,
            "topic_id": "classes-and-objects",
            "level_id": "object-oriented-programming",
            "prompt": "How do C# `record` types differ from standard `class` types by default?",
            "code_snippet": "public record Person(string Name, int Age);",
            "options": [
                "A) Records cannot have methods or properties.",
                "B) Records provide built-in value-based equality, non-destructive mutation (`with`), and formatted `ToString()` by default.",
                "C) Records are allocated on the unmanaged heap without garbage collection.",
                "D) Records cannot be instantiated using the `new` keyword."
            ],
            "correct_option_index": 1
        },
        {
            "id": 4,
            "topic_id": "polymorphism-and-overriding",
            "level_id": "object-oriented-programming",
            "prompt": "What happens if a derived class uses the `new` keyword instead of `override` on a method with the same signature as a virtual base method?",
            "code_snippet": "class Base { public virtual void Print() => Console.WriteLine(\"Base\"); }\nclass Derived : Base { public new void Print() => Console.WriteLine(\"Derived\"); }",
            "options": [
                "A) A compile-time error occurs because virtual methods must be overridden.",
                "B) Calling `Print()` through a `Base` reference pointing to `Derived` outputs 'Derived'.",
                "C) It shadows the base method; calling `Print()` through a `Base` reference outputs 'Base', not 'Derived'.",
                "D) The base class method is erased at runtime."
            ],
            "correct_option_index": 2
        },
        {
            "id": 5,
            "topic_id": "generics-and-constraints",
            "level_id": "intermediate-csharp",
            "prompt": "What does the constraint `where T : class, new()` enforce on a generic parameter `T`?",
            "code_snippet": "public class Repository<T> where T : class, new() { }",
            "options": [
                "A) T must be a reference type with a public parameterless constructor.",
                "B) T must be a struct with at least one constructor.",
                "C) T must implement the INewable interface.",
                "D) T must be sealed."
            ],
            "correct_option_index": 0
        },
        {
            "id": 6,
            "topic_id": "async-await-concurrency",
            "level_id": "intermediate-csharp",
            "prompt": "What is the primary risk of calling `.Result` or `.Wait()` on an incomplete asynchronous Task in a synchronization context (like legacy ASP.NET or UI threads)?",
            "code_snippet": "var data = GetDataAsync().Result;",
            "options": [
                "A) It causes an immediate OutOfMemoryException.",
                "B) It causes thread deadlock because the calling thread blocks waiting for a continuation scheduled on the same thread.",
                "C) It cancels the underlying Task immediately.",
                "D) It turns the asynchronous task into a background worker process."
            ],
            "correct_option_index": 1
        },
        {
            "id": 7,
            "topic_id": "dependency-injection",
            "level_id": "dotnet-and-aspnet-core",
            "prompt": "In ASP.NET Core Dependency Injection, what occurs when a Singleton service injects a Scoped service directly?",
            "code_snippet": None,
            "options": [
                "A) A captive dependency occurs, holding the scoped service instance for the entire application lifetime.",
                "B) The scoped service automatically becomes transient.",
                "C) The application throws a compile-time error.",
                "D) A new scope is automatically created on every method invocation."
            ],
            "correct_option_index": 0
        },
        {
            "id": 8,
            "topic_id": "middleware-pipeline",
            "level_id": "dotnet-and-aspnet-core",
            "prompt": "In an ASP.NET Core HTTP request pipeline, what is the role of `next()` in a middleware delegate?",
            "code_snippet": "app.Use(async (context, next) => { ... await next(); ... });",
            "options": [
                "A) It terminates the request immediately and sends HTTP 200 OK.",
                "B) It executes the next middleware component in the pipeline and awaits its completion.",
                "C) It reboots the web host.",
                "D) It reroutes the request to the nearest controller."
            ],
            "correct_option_index": 1
        },
        {
            "id": 9,
            "topic_id": "efcore-basics-and-dbcontext",
            "level_id": "data-and-efcore",
            "prompt": "When executing a read-only query in EF Core, why is `.AsNoTracking()` recommended?",
            "code_snippet": "var users = await db.Users.AsNoTracking().ToListAsync();",
            "options": [
                "A) It automatically commits an active database transaction.",
                "B) It bypasses change tracking overhead in the DbContext ChangeTracker, saving memory and CPU.",
                "C) It encrypts the SQL connection string in transit.",
                "D) It converts the SQL query into an unindexed full table scan."
            ],
            "correct_option_index": 1
        },
        {
            "id": 10,
            "topic_id": "solid-principles",
            "level_id": "advanced-dotnet",
            "prompt": "Which SOLID principle states that high-level modules should not depend on low-level modules, but both should depend on abstractions?",
            "code_snippet": None,
            "options": [
                "A) Single Responsibility Principle",
                "B) Open-Closed Principle",
                "C) Liskov Substitution Principle",
                "D) Dependency Inversion Principle"
            ],
            "correct_option_index": 3
        }
    ]
    return questions

@router.post("/placement/submit", response_model=PlacementResult)
async def submit_placement_test(payload: PlacementSubmit, db: Session = Depends(get_db)):
    """
    Grades 10-question placement test and unlocks topics accordingly.
    """
    # Answers map
    correct_indices = {1: 0, 2: 1, 3: 1, 4: 2, 5: 0, 6: 1, 7: 0, 8: 1, 9: 1, 10: 3}
    correct_count = 0
    for ans in payload.answers:
        if correct_indices.get(ans.question_id) == ans.selected_option_index:
            correct_count += 1

    score = (correct_count / 10.0) * 100.0

    profile = db.query(UserProfile).first()
    if profile:
        profile.placement_completed = True
        profile.placement_score = score
        db.commit()

    # Determine recommended start topic based on score
    all_topics = db.query(CurriculumTopic).join(CurriculumLevel).order_by(
        CurriculumLevel.order, CurriculumTopic.order
    ).all()

    unlocked_ids = []
    if score >= 90:
        recommended = all_topics[min(15, len(all_topics)-1)]
        unlock_count = 16
        msg = f"Outstanding! High advanced score ({score:.0f}%). You have placed into {recommended.title}."
    elif score >= 70:
        recommended = all_topics[min(10, len(all_topics)-1)]
        unlock_count = 11
        msg = f"Great work! Intermediate score ({score:.0f}%). You have placed into {recommended.title}."
    elif score >= 50:
        recommended = all_topics[min(5, len(all_topics)-1)]
        unlock_count = 6
        msg = f"Solid foundation! Score ({score:.0f}%). You have placed into {recommended.title}."
    else:
        recommended = all_topics[0]
        unlock_count = 1
        msg = f"Welcome to C# & .NET! Score ({score:.0f}%). Starting with foundational topic: {recommended.title}."

    for idx, t in enumerate(all_topics):
        if idx < unlock_count:
            prog = db.query(TopicProgress).filter(TopicProgress.topic_id == t.id).first()
            if prog:
                prog.unlocked = True
                if prog.status == "New":
                    prog.status = "Learning"
                unlocked_ids.append(t.id)

    db.commit()
    return PlacementResult(
        score=score,
        recommended_topic_id=recommended.id,
        recommended_topic_title=recommended.title,
        unlocked_topics=unlocked_ids,
        message=msg
    )

