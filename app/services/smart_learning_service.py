"""
Smart Learning Service for CodeCoach
Implements Phase 2:
1. Adaptive difficulty engine (rule-based, zero LLM)
2. Weak-spot drill generator (one-click 10-question set from most-missed subtopics)
3. "Explain it differently" engine (curated + cached multi-perspective tutor)
4. Concept map graph generator (dependency graph with real-time mastery states)
5. Personal notes & SM-2 spaced repetition flashcards
6. Goal-driven study plan generator with live progress tracking
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case

from app.models import (
    CurriculumLevel, CurriculumTopic, TopicProgress, QuizSet,
    QuizQuestion, QuestionAttempt, PersonalNote, Flashcard,
    StudyPlan, ExplanationCache, utc_now
)
from app.llm.client import llm_client
from app.services.quiz_service import _get_seed_bank_questions

logger = logging.getLogger("codecoach.smart_learning")

# ============================================================================
# 1. ADAPTIVE DIFFICULTY ENGINE (Rule-Based, Zero-LLM)
# ============================================================================

DIFFICULTY_LABELS = {
    1: "Level 1: Foundational",
    2: "Level 2: Core Concepts",
    3: "Level 3: Intermediate",
    4: "Level 4: Advanced Architecture",
    5: "Level 5: Master & Edge Cases"
}

def calculate_adaptive_difficulty_for_subtopic(
    total_attempts: int,
    correct_attempts: int,
    avg_response_time_ms: int
) -> Tuple[int, str, str]:
    """
    Computes recommended difficulty (1-5), difficulty label, and readiness status.
    Pure rule-based logic with zero LLM consumption.
    """
    if total_attempts == 0:
        return 1, DIFFICULTY_LABELS[1], "Unassessed"

    accuracy = correct_attempts / total_attempts if total_attempts > 0 else 0.0

    # Rule matrix based on accuracy and average response time
    if total_attempts >= 3:
        if accuracy >= 0.85 and avg_response_time_ms <= 15000:
            if accuracy >= 0.95 and avg_response_time_ms <= 8000:
                diff = 5
                readiness = "Mastered / High-Velocity"
            elif accuracy >= 0.90:
                diff = 4
                readiness = "Advanced Ready"
            else:
                diff = 3
                readiness = "Solidly Understood"
        elif accuracy >= 0.70 and avg_response_time_ms <= 30000:
            diff = 3
            readiness = "Developing Fluency"
        elif accuracy >= 0.50:
            diff = 2
            readiness = "Reviewing Basics"
        else:
            diff = 1
            readiness = "Needs Remediation"
    else:
        # Initial exploration
        if accuracy >= 0.80:
            diff = 2
            readiness = "Initial Assessment Passed"
        else:
            diff = 1
            readiness = "Foundations in Progress"

    return diff, DIFFICULTY_LABELS[diff], readiness

def get_adaptive_metrics(db: Session, topic_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregates attempt accuracy, response times, and adaptive difficulty recommendations
    grouped by subtopic.
    """
    query = db.query(
        QuizQuestion.subtopic,
        func.count(QuestionAttempt.id).label("total_attempts"),
        func.sum(func.cast(QuestionAttempt.is_correct, func.INTEGER if "sqlite" in str(db.bind.url) else func.INTEGER)).label("correct_attempts"),
        func.avg(func.coalesce(QuestionAttempt.response_time_ms, 12000)).label("avg_time_ms")
    ).join(QuestionAttempt, QuizQuestion.id == QuestionAttempt.question_id)

    if topic_id:
        query = query.filter(QuizQuestion.topic_id == topic_id)

    query = query.filter(QuizQuestion.subtopic.isnot(None)).group_by(QuizQuestion.subtopic)
    rows = query.all()

    subtopics_metrics = []
    diff_sum = 0
    count = 0

    for row in rows:
        subtopic = row[0]
        total = int(row[1] or 0)
        correct = int(row[2] or 0)
        avg_time = int(row[3] or 12000)
        acc = round((correct / total) * 100.0, 1) if total > 0 else 0.0

        rec_diff, diff_label, readiness = calculate_adaptive_difficulty_for_subtopic(total, correct, avg_time)
        diff_sum += rec_diff
        count += 1

        subtopics_metrics.append({
            "subtopic": subtopic,
            "total_attempts": total,
            "correct_attempts": correct,
            "accuracy_pct": acc,
            "avg_response_time_ms": avg_time,
            "recommended_difficulty": rec_diff,
            "difficulty_label": diff_label,
            "readiness_status": readiness
        })

    # Sort: weakest subtopics first
    subtopics_metrics.sort(key=lambda s: (s["accuracy_pct"], -s["total_attempts"]))

    overall_diff = max(1, min(5, round(diff_sum / count))) if count > 0 else 1

    return {
        "topic_id": topic_id,
        "overall_recommended_difficulty": overall_diff,
        "subtopics": subtopics_metrics
    }


# ============================================================================
# 2. WEAK-SPOT DRILL GENERATOR (One-Click 10-Question Targeted Set)
# ============================================================================

def get_weak_spots(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Identifies the user's top most-missed subtopics across all quiz attempts.
    """
    rows = db.query(
        QuizQuestion.subtopic,
        QuizQuestion.topic_id,
        func.count(QuestionAttempt.id).label("total_attempts"),
        func.sum(case((QuestionAttempt.is_correct == False, 1), else_=0)).label("miss_count")
    ).join(QuestionAttempt, QuizQuestion.id == QuestionAttempt.question_id)\
     .filter(QuizQuestion.subtopic.isnot(None))\
     .group_by(QuizQuestion.subtopic, QuizQuestion.topic_id)\
     .having(func.sum(case((QuestionAttempt.is_correct == False, 1), else_=0)) > 0)\
     .order_by(desc("miss_count"))\
     .limit(limit).all()

    weak_spots = []
    for r in rows:
        subtopic = r[0]
        t_id = r[1]
        tot = int(r[2] or 0)
        misses = int(r[3] or 0)
        acc = round(((tot - misses) / tot) * 100.0, 1) if tot > 0 else 0.0

        topic_obj = db.query(CurriculumTopic).filter(CurriculumTopic.id == t_id).first()
        topic_title = topic_obj.title if topic_obj else t_id

        weak_spots.append({
            "subtopic": subtopic,
            "topic_id": t_id,
            "topic_title": topic_title,
            "miss_count": misses,
            "accuracy_pct": acc
        })

    return weak_spots

def create_weak_spot_drill(db: Session, user_session_id: Optional[str] = None) -> Tuple[QuizSet, List[str]]:
    """
    Generates a high-yield 10-question drill built strictly from the user's most-missed subtopics.
    Prioritizes actual missed questions first, then fills from curated bank questions for those weak subtopics.
    """
    weak_subtopics_data = get_weak_spots(db, limit=4)
    target_subtopics = [w["subtopic"] for w in weak_subtopics_data]

    # Target primary topic for set grouping (default to variables-and-types if none)
    primary_topic_id = weak_subtopics_data[0]["topic_id"] if weak_subtopics_data else "variables-and-types"

    # Step 1: Pull previously missed questions that haven't been cleared (needs_review == True)
    missed_questions_query = db.query(QuizQuestion).join(QuestionAttempt).filter(
        QuestionAttempt.needs_review == True
    ).distinct().limit(10).all()

    selected_question_dicts = []
    used_prompts = set()

    for q in missed_questions_query:
        if q.prompt not in used_prompts:
            used_prompts.add(q.prompt)
            selected_question_dicts.append({
                "question_type": q.question_type,
                "prompt": q.prompt,
                "code_snippet": q.code_snippet,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "hint": q.hint or "Focus on edge case semantics.",
                "difficulty": q.difficulty,
                "subtopic": q.subtopic or (target_subtopics[0] if target_subtopics else "Core C#")
            })

    # Step 2: If we have fewer than 10, pull curated questions matching the weak subtopics
    if len(selected_question_dicts) < 10:
        for t_info in (weak_subtopics_data or [{"topic_id": "variables-and-types", "subtopic": "value vs reference types"}]):
            seed_qs = _get_seed_bank_questions(t_info["topic_id"], set_size=15)
            for sq in seed_qs:
                if len(selected_question_dicts) >= 10:
                    break
                if sq.get("prompt") not in used_prompts:
                    # Match subtopic or take highest yield
                    used_prompts.add(sq.get("prompt"))
                    selected_question_dicts.append({
                        "question_type": sq.get("question_type", "mcq"),
                        "prompt": sq.get("prompt"),
                        "code_snippet": sq.get("code_snippet"),
                        "options": sq.get("options", []),
                        "correct_answer": sq.get("correct_answer"),
                        "explanation": sq.get("explanation"),
                        "hint": sq.get("hint"),
                        "difficulty": sq.get("difficulty", 2),
                        "subtopic": sq.get("subtopic") or t_info.get("subtopic", "Core C#")
                    })

    # Step 3: If still under 10 (e.g. brand new user with 0 misses), populate high-yield C# edge cases
    if len(selected_question_dicts) < 10:
        defaults = [
            {
                "prompt": "What is the primary architectural difference between a struct (value type) and a class (reference type) in .NET?",
                "code_snippet": "struct Point { public int X; public int Y; }\nclass Box { public int W; }",
                "options": [
                    "A) Structs are allocated on the stack (or inline in containing type) and copied by value; classes are heap-allocated with reference semantics.",
                    "B) Structs support inheritance while classes do not.",
                    "C) Structs can have finalizers, but classes cannot.",
                    "D) Structs cannot implement interfaces."
                ],
                "correct_answer": "A",
                "explanation": "Structs have value semantics and are copied field-by-field. Classes have reference semantics where only the reference pointer is copied.",
                "subtopic": "value vs reference types"
            },
            {
                "prompt": "When should 'ValueTask<T>' be preferred over 'Task<T>' in high-throughput C# code?",
                "code_snippet": "public ValueTask<int> GetCachedCountAsync() =>\n    _cacheHit ? new ValueTask<int>(_cached) : new ValueTask<int>(FetchAsync());",
                "options": [
                    "A) When the method often completes synchronously, avoiding heap allocations for Task<T> instances.",
                    "B) When the method runs indefinitely in the background.",
                    "C) When multiple consumers need to await the same instance concurrently.",
                    "D) When targeting .NET Framework 3.5."
                ],
                "correct_answer": "A",
                "explanation": "ValueTask is a discriminated union struct. When the result is immediately available (synchronous completion), it requires zero heap allocation.",
                "subtopic": "async/await & performance"
            },
            {
                "prompt": "Why does evaluating an 'IEnumerable<T>' query with multiple '.Count()' and '.First()' calls degrade performance?",
                "code_snippet": "var items = dbContext.Users.Where(u => u.IsActive);\nif (items.Count() > 0) Process(items.First());",
                "options": [
                    "A) Deferred execution causes multiple roundtrips and enumerations of the underlying sequence.",
                    "B) IEnumerable locks the thread permanently after one query.",
                    "C) C# compiler refuses to compile multiple LINQ methods.",
                    "D) Count() clears the sequence buffer."
                ],
                "correct_answer": "A",
                "explanation": "LINQ operators have deferred execution. Calling Count() and First() separately re-enumerates the sequence twice.",
                "subtopic": "collections & linq"
            }
        ]
        for d in defaults:
            if len(selected_question_dicts) >= 10:
                break
            if d["prompt"] not in used_prompts:
                used_prompts.add(d["prompt"])
                selected_question_dicts.append({
                    "question_type": "mcq",
                    "prompt": d["prompt"],
                    "code_snippet": d.get("code_snippet"),
                    "options": d["options"],
                    "correct_answer": d["correct_answer"],
                    "explanation": d["explanation"],
                    "hint": "Think about memory allocation and deferred evaluation in .NET.",
                    "difficulty": 3,
                    "subtopic": d["subtopic"]
                })

    # Limit to exactly 10 questions
    selected_question_dicts = selected_question_dicts[:10]

    # Create new QuizSet
    latest_set = db.query(QuizSet).filter(QuizSet.topic_id == primary_topic_id).order_by(QuizSet.set_number.desc()).first()
    set_num = (latest_set.set_number + 1) if latest_set else 1

    drill_set = QuizSet(
        topic_id=primary_topic_id,
        set_number=set_num,
        is_retry_set=True,
        total_questions=len(selected_question_dicts),
        completed=False,
        weak_subtopics_json=json.dumps(target_subtopics)
    )
    db.add(drill_set)
    db.flush()

    for idx, q_data in enumerate(selected_question_dicts, start=1):
        q_obj = QuizQuestion(
            set_id=drill_set.id,
            topic_id=primary_topic_id,
            question_index=idx,
            question_type=q_data.get("question_type", "mcq"),
            prompt=q_data.get("prompt"),
            code_snippet=q_data.get("code_snippet"),
            options_json=json.dumps(q_data.get("options", [])),
            correct_answer=q_data.get("correct_answer"),
            explanation=q_data.get("explanation"),
            hint=q_data.get("hint"),
            difficulty=q_data.get("difficulty", 2),
            subtopic=q_data.get("subtopic")
        )
        db.add(q_obj)

    db.commit()
    logger.info("Created Weak-Spot Drill set #%s with %s questions for topics %s", drill_set.id, len(selected_question_dicts), target_subtopics)
    return drill_set, target_subtopics


# ============================================================================
# 3. "EXPLAIN IT DIFFERENTLY" ENGINE (Cached Multi-Perspective Tutor)
# ============================================================================

PRE_CURATED_EXPLANATIONS = {
    ("span<t>", "analogy"): (
        "Think of a physical book in a library. A standard C# string or array copy is like photocopying 500 pages just to inspect page 42. "
        "A `Span<T>` is like placing a small magnifying glass window directly over line 42 on the existing book page: you inspect or mutate "
        "the exact physical memory instantly without moving, copying, or allocating a single atom of heap memory."
    ),
    ("span<t>", "simplified"): (
        "`Span<T>` lets you view a slice of an array, string, or memory buffer without creating a new copy. "
        "Because it's a `ref struct` that lives only on the stack, it produces zero garbage collector pressure, making your code run much faster."
    ),
    ("span<t>", "code_first"): (
        "```csharp\n"
        "// Allocates ZERO heap memory\n"
        "string header = \"AUTHORIZATION: Bearer token_xyz123\";\n"
        "ReadOnlySpan<char> span = header.AsSpan();\n\n"
        "// Slice the prefix directly without copying string\n"
        "ReadOnlySpan<char> token = span.Slice(22);\n"
        "Console.WriteLine(token.ToString()); // token_xyz123\n"
        "```\n"
        "Slice() creates a lightweight pointer + length window into existing memory without allocating a new string on the managed heap."
    ),
    ("async/await", "analogy"): (
        "Imagine ordering coffee at a busy Gotham café. A synchronous method stands at the counter frozen, refusing to let anyone else order until the barista grinds, brews, and pours the coffee. "
        "An `async/await` method takes a buzzer pager (a Task), immediately steps away from the counter so the cashier thread can serve other customers, and only steps back up when the buzzer vibrates."
    ),
    ("async/await", "simplified"): (
        "`async` and `await` prevent your app from freezing while waiting for slow operations like databases or web requests. "
        "While waiting, the thread is released to do other work, and returns when the data is ready."
    ),
    ("async/await", "code_first"): (
        "```csharp\n"
        "// Thread is NOT blocked during I/O wait\n"
        "public async Task<string> FetchPayloadAsync(HttpClient client, string url)\n"
        "{\n"
        "    // Execution pauses here, freeing the thread to handle other HTTP requests\n"
        "    HttpResponseMessage response = await client.GetAsync(url);\n"
        "    return await response.Content.ReadAsStringAsync();\n"
        "}\n"
        "```"
    ),
    ("record types", "analogy"): (
        "A regular class in C# is like a passport: its identity is tied to its unique passport number (memory address). Even if two people have identical names and ages, they are different passport objects. "
        "A `record` is like a $100 bill: two bills with identical denominations have identical value equality; you care about the contents, not the memory pointer."
    ),
    ("record types", "simplified"): (
        "Records in C# are reference types that automatically compare their values rather than their memory references. "
        "They give you built-in value equality, clean `ToString()` printing, and non-destructive mutation using the `with` expression."
    ),
    ("record types", "code_first"): (
        "```csharp\n"
        "// Value equality & immutability in one line\n"
        "public record UserProfile(int Id, string Username, string Role);\n\n"
        "var u1 = new UserProfile(1, \"bwayne\", \"Admin\");\n"
        "var u2 = new UserProfile(1, \"bwayne\", \"Admin\");\n\n"
        "Console.WriteLine(u1 == u2); // True! Compared by value, not pointer.\n"
        "var u3 = u1 with { Role = \"DarkKnight\" }; // Non-destructive copy\n"
        "```"
    )
}

async def explain_concept_differently(
    db: Session,
    concept: str,
    current_explanation: str,
    perspective: str,
    context_code: Optional[str] = None
) -> Tuple[str, bool]:
    """
    Returns an alternate explanation (analogy, simplified ELI5, or code-first)
    with database and in-memory caching to avoid unnecessary LLM calls.
    """
    perspective = perspective.lower().strip()
    if perspective not in ("analogy", "simplified", "code_first"):
        perspective = "simplified"

    clean_concept = concept.strip().lower()
    norm_key = clean_concept.replace(" ", "").replace("<t>", "").replace("()", "")

    # Check pre-curated dictionary first
    for (k_concept, k_persp), canned_text in PRE_CURATED_EXPLANATIONS.items():
        if k_persp == perspective and (k_concept in clean_concept or clean_concept in k_concept):
            return canned_text, True

    # Generate unique hash for DB cache
    cache_hash = hashlib.sha256(f"{norm_key}:{perspective}:{(context_code or '')[:100]}".encode()).hexdigest()

    cached_entry = db.query(ExplanationCache).filter(ExplanationCache.cache_key == cache_hash).first()
    if cached_entry:
        return cached_entry.explanation, True

    # Build targeted prompt
    if perspective == "analogy":
        system_instruction = (
            "You are CodeCoach's Gotham-Noir tutor. Explain the C#/.NET concept using an intuitive, vivid real-world or architectural engineering metaphor. "
            "Keep it under 150 words. Be concrete, memorable, and clear."
        )
        user_prompt = f"Concept: {concept}\nCurrent Explanation: {current_explanation}\nCode Context: {context_code or 'None'}\n\nProvide the metaphorical analogy explanation:"
    elif perspective == "simplified":
        system_instruction = (
            "You are CodeCoach. Explain this C#/.NET concept as an ELI5 (Explain Like I'm 5) breakdown in simple, direct English. "
            "Ban unnecessary academic jargon. Focus on why the developer cares and how it helps them build better software. Under 120 words."
        )
        user_prompt = f"Concept: {concept}\nCurrent Explanation: {current_explanation}\n\nProvide the simplified ELI5 explanation:"
    else: # code_first
        system_instruction = (
            "You are CodeCoach. Provide a minimal, runnable, idiomatically modern C# 13 snippet that teaches the concept before any text. "
            "Include inline comments pointing out the crucial mechanism, followed by a 2-sentence summary."
        )
        user_prompt = f"Concept: {concept}\nCurrent Explanation: {current_explanation}\nCode Context: {context_code or 'None'}\n\nProvide the code-first snippet and concise takeaway:"

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt}
    ]

    try:
        explanation_text = await llm_client.generate_chat_completion(messages=messages, max_tokens=350, temperature=0.3)
        if not explanation_text:
            explanation_text = f"Alternative perspective on {concept}: {current_explanation}"
    except Exception as e:
        logger.warning("LLM explain differently call failed: %s; serving heuristic fallback.", e)
        explanation_text = f"Alternative view on {concept}: In modern C# .NET 9, this mechanism guarantees high performance, safety, and strict type verification."

    # Cache in database
    new_cache = ExplanationCache(
        cache_key=cache_hash,
        concept=concept[:255],
        perspective=perspective,
        explanation=explanation_text
    )
    db.add(new_cache)
    db.commit()

    return explanation_text, False


# ============================================================================
# 4. CONCEPT MAP GRAPH ENGINE (Interactive Dependency Graph)
# ============================================================================

CONCEPT_DEPENDENCY_EDGES = [
    # Level 1: Basics
    {"source": "variables-and-types", "target": "operators-and-expressions", "relationship_type": "prerequisite"},
    {"source": "operators-and-expressions", "target": "conditions-and-branching", "relationship_type": "prerequisite"},
    {"source": "conditions-and-branching", "target": "loops-and-iterations", "relationship_type": "prerequisite"},
    {"source": "loops-and-iterations", "target": "methods-and-parameters", "relationship_type": "prerequisite"},
    {"source": "methods-and-parameters", "target": "arrays-and-spans", "relationship_type": "prerequisite"},
    
    # Bridge L1 -> L2
    {"source": "arrays-and-spans", "target": "classes-and-objects", "relationship_type": "evolution"},
    
    # Level 2: OOP
    {"source": "classes-and-objects", "target": "encapsulation-and-access", "relationship_type": "prerequisite"},
    {"source": "encapsulation-and-access", "target": "inheritance-and-base", "relationship_type": "prerequisite"},
    {"source": "inheritance-and-base", "target": "polymorphism-and-overriding", "relationship_type": "prerequisite"},
    {"source": "polymorphism-and-overriding", "target": "interfaces-and-abstraction", "relationship_type": "prerequisite"},
    {"source": "interfaces-and-abstraction", "target": "generics-in-csharp", "relationship_type": "evolution"},

    # Bridge L2 -> L3
    {"source": "generics-in-csharp", "target": "collections-and-linq", "relationship_type": "prerequisite"},

    # Level 3: Advanced
    {"source": "collections-and-linq", "target": "delegates-and-lambdas", "relationship_type": "synergy"},
    {"source": "delegates-and-lambdas", "target": "async-await-and-tasks", "relationship_type": "prerequisite"},
    {"source": "async-await-and-tasks", "target": "exception-handling", "relationship_type": "synergy"},
    {"source": "exception-handling", "target": "memory-spans-and-performance", "relationship_type": "evolution"},

    # Bridge L3 -> L4
    {"source": "async-await-and-tasks", "target": "dotnet-runtime-and-clr", "relationship_type": "prerequisite"},

    # Level 4: .NET & Web API
    {"source": "dotnet-runtime-and-clr", "target": "dependency-injection", "relationship_type": "prerequisite"},
    {"source": "dependency-injection", "target": "aspnet-core-web-api", "relationship_type": "prerequisite"},
    {"source": "aspnet-core-web-api", "target": "entity-framework-core", "relationship_type": "synergy"},
    {"source": "entity-framework-core", "target": "middleware-and-security", "relationship_type": "evolution"},
    {"source": "generics-in-csharp", "target": "entity-framework-core", "relationship_type": "synergy"}
]

def get_concept_map_data(db: Session) -> Dict[str, Any]:
    """
    Generates node-link graph data representing curriculum progression and user mastery.
    """
    topics = db.query(CurriculumTopic).join(CurriculumLevel).order_by(CurriculumLevel.order, CurriculumTopic.order).all()
    progress_map = {p.topic_id: p for p in db.query(TopicProgress).all()}

    # Compute incoming prerequisites per node
    incoming_prereqs: Dict[str, List[str]] = {}
    for edge in CONCEPT_DEPENDENCY_EDGES:
        incoming_prereqs.setdefault(edge["target"], []).append(edge["source"])

    nodes = []
    mastered_count = 0
    learning_count = 0
    locked_count = 0

    for topic in topics:
        prog = progress_map.get(topic.id)
        status = prog.status if prog else "Locked"
        unlocked = prog.unlocked if prog else False
        highest_score = prog.highest_score if prog else 0.0

        if not unlocked and status != "Mastered":
            status = "Locked"

        if status == "Mastered":
            mastered_count += 1
        elif status in ("Learning", "Reviewing"):
            learning_count += 1
        else:
            locked_count += 1

        nodes.append({
            "id": topic.id,
            "level_id": topic.level_id,
            "level_title": topic.level.title if topic.level else "",
            "title": topic.title,
            "order": topic.order,
            "status": status,
            "mastery_score": highest_score,
            "subtopics": topic.subtopics,
            "unlocked": unlocked,
            "prerequisites": incoming_prereqs.get(topic.id, [])
        })

    return {
        "nodes": nodes,
        "edges": CONCEPT_DEPENDENCY_EDGES,
        "total_nodes": len(nodes),
        "mastered_nodes": mastered_count,
        "learning_nodes": learning_count,
        "locked_nodes": locked_count
    }


# ============================================================================
# 5. PERSONAL NOTES & SM-2 SPACED REPETITION FLASHCARDS
# ============================================================================

def create_personal_note(
    db: Session,
    title: str,
    content: str,
    topic_id: Optional[str] = None,
    tags: List[str] = None,
    user_session_id: Optional[str] = None
) -> PersonalNote:
    """
    Saves an answer or concept as a personal note.
    """
    note = PersonalNote(
        user_session_id=user_session_id,
        topic_id=topic_id,
        title=title.strip(),
        content=content.strip(),
        tags_json=json.dumps(tags or [])
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note

def list_personal_notes(db: Session, user_session_id: Optional[str] = None) -> List[PersonalNote]:
    """
    Lists personal notes.
    """
    query = db.query(PersonalNote).order_by(PersonalNote.id.desc())
    if user_session_id:
        query = query.filter(PersonalNote.user_session_id == user_session_id)
    return query.all()

def delete_personal_note(db: Session, note_id: int) -> bool:
    """
    Deletes a personal note.
    """
    note = db.query(PersonalNote).filter(PersonalNote.id == note_id).first()
    if not note:
        return False
    db.delete(note)
    db.commit()
    return True

def generate_flashcards_from_missed_questions(db: Session, user_session_id: Optional[str] = None) -> List[Flashcard]:
    """
    Auto-generates high-yield flashcards from missed questions (needs_review == True).
    100% Zero-LLM algorithm: instant and free-tier friendly.
    """
    missed_questions = db.query(QuizQuestion).join(QuestionAttempt).filter(
        QuestionAttempt.needs_review == True
    ).distinct().all()

    existing_fronts = {
        row[0] for row in db.query(Flashcard.front).all()
    }

    created_cards = []
    now = utc_now()

    for q in missed_questions:
        if q.prompt in existing_fronts:
            continue

        card = Flashcard(
            user_session_id=user_session_id,
            topic_id=q.topic_id,
            subtopic=q.subtopic,
            front=q.prompt,
            back=f"**Correct Answer:** {q.correct_answer}\n\n{q.explanation}",
            code_snippet=q.code_snippet,
            source_type="missed_question",
            interval_days=1,
            ease_factor=2.5,
            repetitions=0,
            due_date=now
        )
        db.add(card)
        created_cards.append(card)
        existing_fronts.add(q.prompt)

    if created_cards:
        db.commit()
        for c in created_cards:
            db.refresh(c)

    logger.info("Auto-generated %d flashcards from missed questions", len(created_cards))
    return created_cards

def generate_flashcards_from_note(db: Session, note_id: int) -> List[Flashcard]:
    """
    Generates Q&A flashcards from a saved personal note.
    """
    note = db.query(PersonalNote).filter(PersonalNote.id == note_id).first()
    if not note:
        raise ValueError(f"Note {note_id} not found.")

    # Rule-based extraction from lines or bullet points
    lines = [l.strip() for l in note.content.split("\n") if l.strip()]
    created_cards = []
    now = utc_now()

    # Look for bullet points or Q&A patterns
    q_pairs = []
    for line in lines:
        if ":" in line and not line.startswith("http"):
            parts = line.split(":", 1)
            q_pairs.append((parts[0].strip(" -*"), parts[1].strip()))

    if not q_pairs:
        # Single card summarizing the note
        q_pairs.append((f"What are the key concepts of '{note.title}'?", note.content))

    for front_txt, back_txt in q_pairs[:4]:
        card = Flashcard(
            user_session_id=note.user_session_id,
            note_id=note.id,
            topic_id=note.topic_id,
            front=front_txt,
            back=back_txt,
            source_type="note",
            interval_days=1,
            ease_factor=2.5,
            repetitions=0,
            due_date=now
        )
        db.add(card)
        created_cards.append(card)

    db.commit()
    for c in created_cards:
        db.refresh(c)
    return created_cards

def get_due_flashcards(db: Session, user_session_id: Optional[str] = None) -> List[Flashcard]:
    """
    Retrieves flashcards due for review according to the SM-2 schedule.
    """
    now = utc_now()
    query = db.query(Flashcard).filter(Flashcard.due_date <= now).order_by(Flashcard.due_date.asc())
    if user_session_id:
        query = query.filter(Flashcard.user_session_id == user_session_id)
    return query.all()

def review_flashcard_sm2(db: Session, card_id: int, rating: int) -> Dict[str, Any]:
    """
    Evaluates recall with the SuperMemo SM-2 algorithm:
    rating:
      1: Again (Complete blackout / incorrect recall)
      2: Hard (Correct with serious hesitation)
      3: Good (Correct response after deliberate thought)
      4: Easy (Perfect immediate recall)
    """
    card = db.query(Flashcard).filter(Flashcard.id == card_id).first()
    if not card:
        raise ValueError(f"Flashcard {card_id} not found.")

    rating = max(1, min(4, rating))
    now = utc_now()

    if rating == 1:
        # Reset interval on failure
        card.repetitions = 0
        card.interval_days = 1
        card.ease_factor = max(1.3, card.ease_factor - 0.2)
    elif rating == 2:
        # Hard: slight increment
        card.repetitions += 1
        card.interval_days = max(1, int(card.interval_days * 1.2))
        card.ease_factor = max(1.3, card.ease_factor - 0.15)
    elif rating == 3:
        # Good: standard SM-2 progression
        if card.repetitions == 0:
            card.interval_days = 1
        elif card.repetitions == 1:
            card.interval_days = 3
        else:
            card.interval_days = int(card.interval_days * card.ease_factor)
        card.repetitions += 1
    else: # 4: Easy
        if card.repetitions == 0:
            card.interval_days = 3
        else:
            card.interval_days = int(card.interval_days * card.ease_factor * 1.3)
        card.ease_factor = min(3.0, card.ease_factor + 0.15)
        card.repetitions += 1

    card.last_reviewed_at = now
    card.due_date = now + timedelta(days=card.interval_days)
    db.commit()

    return {
        "id": card.id,
        "rating": rating,
        "new_interval_days": card.interval_days,
        "new_ease_factor": round(card.ease_factor, 2),
        "repetitions": card.repetitions,
        "next_due_date": card.due_date.isoformat()
    }


# ============================================================================
# 6. STUDY PLAN GENERATOR (Goal-Driven Dynamic Timeline)
# ============================================================================

PRESET_STUDY_PLANS = [
    {
        "target_role": "Junior .NET Developer",
        "goal_title": "Junior .NET Core Job in 8 Weeks",
        "duration_weeks": 8,
        "daily_minutes": 30,
        "weeks": [
            {
                "week_number": 1,
                "title": "C# Types, Control Flow & Methods",
                "topic_ids": ["variables-and-types", "operators-and-expressions", "conditions-and-branching", "loops-and-iterations", "methods-and-parameters"],
                "goal_description": "Master value vs reference types, null-coalescing operators, pattern matching switch, and method parameter modifiers."
            },
            {
                "week_number": 2,
                "title": "Arrays, Strings & OOP Foundations",
                "topic_ids": ["arrays-and-spans", "classes-and-objects", "encapsulation-and-access"],
                "goal_description": "Learn string immutability, Span<T> intro, primary constructors, record types, and access modifier encapsulation."
            },
            {
                "week_number": 3,
                "title": "Polymorphism, Interfaces & Generics",
                "topic_ids": ["inheritance-and-base", "polymorphism-and-overriding", "interfaces-and-abstraction", "generics-in-csharp"],
                "goal_description": "Implement interface contracts, virtual/override mechanics, sealed classes, and generic constraints (where T : class)."
            },
            {
                "week_number": 4,
                "title": "Collections & Fluent LINQ Mastery",
                "topic_ids": ["collections-and-linq", "delegates-and-lambdas"],
                "goal_description": "Write idiomatic LINQ with deferred execution awareness, lambdas, Func/Action delegates, and Dictionary lookup optimization."
            },
            {
                "week_number": 5,
                "title": "Modern Asynchronous Programming (async/await)",
                "topic_ids": ["async-await-and-tasks", "exception-handling"],
                "goal_description": "Avoid async void traps, configure ConfigureAwait, handle aggregate exceptions, and implement structured try/catch/finally."
            },
            {
                "week_number": 6,
                "title": "High-Performance Memory & .NET CLR",
                "topic_ids": ["memory-spans-and-performance", "dotnet-runtime-and-clr"],
                "goal_description": "Understand garbage collection generations (Gen 0/1/2), stack vs heap, ref struct rules, and memory pooling."
            },
            {
                "week_number": 7,
                "title": "ASP.NET Core Web API & Dependency Injection",
                "topic_ids": ["dependency-injection", "aspnet-core-web-api"],
                "goal_description": "Build production Minimal APIs, understand Transient/Scoped/Singleton service lifetimes, and configure route filters."
            },
            {
                "week_number": 8,
                "title": "Entity Framework Core & Middleware Security",
                "topic_ids": ["entity-framework-core", "middleware-and-security"],
                "goal_description": "Execute database migrations, handle DbContext concurrency, prevent SQL injection, and configure JWT authentication middleware."
            }
        ]
    },
    {
        "target_role": "Mid-Level C# Backend Specialist",
        "goal_title": "Enterprise C# & .NET 9 Specialist in 6 Weeks",
        "duration_weeks": 6,
        "daily_minutes": 45,
        "weeks": [
            {
                "week_number": 1,
                "title": "Modern C# 13 Idioms & Records",
                "topic_ids": ["variables-and-types", "classes-and-objects", "generics-in-csharp"],
                "goal_description": "Master primary constructors, record structs, pattern matching relational patterns, and generic covariance/contravariance."
            },
            {
                "week_number": 2,
                "title": "High-Throughput LINQ & Collection Internals",
                "topic_ids": ["collections-and-linq", "delegates-and-lambdas"],
                "goal_description": "Eliminate multiple enumeration leaks, optimize hash-based collections, and implement custom iterator blocks with yield return."
            },
            {
                "week_number": 3,
                "title": "Resilient Asynchronous Pipelines",
                "topic_ids": ["async-await-and-tasks", "exception-handling"],
                "goal_description": "Implement CancellationToken propagation, ValueTask optimization, Task.WhenAll with exception throttling, and retry policies."
            },
            {
                "week_number": 4,
                "title": "Zero-Allocation C# (Span, Memory & Unsafe)",
                "topic_ids": ["memory-spans-and-performance", "dotnet-runtime-and-clr"],
                "goal_description": "Master ReadOnlySpan, MemoryPool, ArrayPool<T>, GC pauses, and pinned buffer interop."
            },
            {
                "week_number": 5,
                "title": "Clean Web API Architecture & DI",
                "topic_ids": ["dependency-injection", "aspnet-core-web-api"],
                "goal_description": "Design decoupled clean architecture with CQRS, MediatR patterns, custom DI container scopes, and problem details responses."
            },
            {
                "week_number": 6,
                "title": "Production EF Core & Defense-in-Depth",
                "topic_ids": ["entity-framework-core", "middleware-and-security"],
                "goal_description": "Debug generated SQL queries, resolve N+1 queries with AsSplitQuery, configure optimistic concurrency tokens, and secure middleware."
            }
        ]
    }
]

def get_study_plan_presets() -> List[Dict[str, Any]]:
    """
    Returns preset curriculum study plan outlines.
    """
    return PRESET_STUDY_PLANS

def create_or_update_study_plan(
    db: Session,
    goal_title: str,
    target_role: str = "Junior .NET Developer",
    duration_weeks: int = 8,
    daily_minutes: int = 30,
    user_session_id: Optional[str] = None
) -> StudyPlan:
    """
    Generates or refreshes the user's active study plan.
    """
    # Deactivate existing plans for this session
    existing_plans = db.query(StudyPlan).filter(StudyPlan.is_active == True)
    if user_session_id:
        existing_plans = existing_plans.filter(StudyPlan.user_session_id == user_session_id)
    for p in existing_plans.all():
        p.is_active = False

    # Match preset or generate structured weeks
    matched_preset = next((p for p in PRESET_STUDY_PLANS if p["target_role"].lower() == target_role.lower() or p["duration_weeks"] == duration_weeks), None)
    if matched_preset:
        weeks_data = matched_preset["weeks"]
    else:
        # Distribute curriculum topics across requested duration_weeks
        all_topics = db.query(CurriculumTopic).all()
        t_ids = [t.id for t in all_topics]
        chunk_size = max(1, len(t_ids) // max(1, duration_weeks))
        weeks_data = []
        for w_idx in range(1, duration_weeks + 1):
            start_i = (w_idx - 1) * chunk_size
            end_i = start_i + chunk_size if w_idx < duration_weeks else len(t_ids)
            sub_ids = t_ids[start_i:end_i]
            weeks_data.append({
                "week_number": w_idx,
                "title": f"Milestone Week {w_idx}: Focused .NET Competency",
                "topic_ids": sub_ids,
                "goal_description": f"Master the verification gates for {len(sub_ids)} core C# curriculum topics."
            })

    start = utc_now()
    target_dt = start + timedelta(weeks=duration_weeks)

    plan = StudyPlan(
        user_session_id=user_session_id,
        goal_title=goal_title.strip(),
        target_role=target_role.strip(),
        duration_weeks=duration_weeks,
        daily_minutes=daily_minutes,
        start_date=start,
        target_date=target_dt,
        weeks_json=json.dumps(weeks_data),
        current_week=1,
        is_active=True
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

def get_active_study_plan_with_progress(db: Session, user_session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Returns the user's active study plan annotated with live progress per week and topic.
    """
    query = db.query(StudyPlan).filter(StudyPlan.is_active == True).order_by(StudyPlan.id.desc())
    if user_session_id:
        query = query.filter(StudyPlan.user_session_id == user_session_id)
    plan = query.first()

    if not plan:
        return None

    progress_map = {p.topic_id: p for p in db.query(TopicProgress).all()}
    topics_map = {t.id: t.title for t in db.query(CurriculumTopic).all()}

    weeks = plan.weeks
    annotated_weeks = []
    total_topics_all = 0
    completed_topics_all = 0
    current_active_week = 1
    found_active = False

    for w in weeks:
        w_topics = w.get("topic_ids", [])
        w_titles = [topics_map.get(tid, tid) for tid in w_topics]
        
        # Calculate completion in this week
        w_total = len(w_topics)
        w_completed = 0
        for tid in w_topics:
            prog = progress_map.get(tid)
            if prog and (prog.status == "Mastered" or prog.sets_completed > 0):
                w_completed += 1

        total_topics_all += w_total
        completed_topics_all += w_completed

        prog_pct = round((w_completed / w_total) * 100.0, 1) if w_total > 0 else 0.0
        is_week_done = (w_completed >= w_total) if w_total > 0 else False

        if not is_week_done and not found_active:
            current_active_week = w.get("week_number", 1)
            found_active = True

        annotated_weeks.append({
            "week_number": w.get("week_number"),
            "title": w.get("title"),
            "topic_ids": w_topics,
            "topic_titles": w_titles,
            "goal_description": w.get("goal_description"),
            "completed": is_week_done,
            "progress_pct": prog_pct
        })

    # If all weeks complete, current_week is the final week
    if not found_active and weeks:
        current_active_week = len(weeks)

    overall_pct = round((completed_topics_all / total_topics_all) * 100.0, 1) if total_topics_all > 0 else 0.0

    return {
        "id": plan.id,
        "goal_title": plan.goal_title,
        "target_role": plan.target_role,
        "duration_weeks": plan.duration_weeks,
        "daily_minutes": plan.daily_minutes,
        "start_date": plan.start_date.isoformat(),
        "target_date": plan.target_date.isoformat() if plan.target_date else None,
        "current_week": current_active_week,
        "is_active": plan.is_active,
        "weeks": annotated_weeks,
        "overall_progress_pct": overall_pct
    }
