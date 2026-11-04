"""
Output Predictor Service for CodeCoach
60-second timed speed rounds of "What does this C# code print?".
Evaluates answers instantaneously with zero LLM cost, calculates streak multipliers and speed bonuses.
"""

import uuid
import random
from typing import Dict, Any, List

CURATED_PREDICTOR_QUESTIONS = [
    {
        "id": "pred-value-vs-ref-struct",
        "topic_id": "variables-and-types",
        "title": "Struct Copy Semantics",
        "code_snippet": """public struct Point
{
    public int X;
}

Point p1 = new Point { X = 10 };
Point p2 = p1;
p2.X = 25;

Console.WriteLine($"{p1.X}, {p2.X}");""",
        "options": [
            "A) 10, 25",
            "B) 25, 25",
            "C) 10, 10",
            "D) Compilation Error"
        ],
        "correct_output": "A",
        "explanation": "Structs in C# are value types. Assigning 'p2 = p1' creates an independent copy on the stack, so mutating p2.X does not alter p1.X."
    },
    {
        "id": "pred-linq-deferred-execution",
        "topic_id": "linq-fundamentals",
        "title": "Deferred LINQ Execution",
        "code_snippet": """var numbers = new List<int> { 1, 2, 3 };
var query = numbers.Select(n => n * 10);

numbers.Add(4);

Console.WriteLine(string.Join(", ", query));""",
        "options": [
            "A) 10, 20, 30",
            "B) 10, 20, 30, 40",
            "C) 1, 2, 3, 4",
            "D) 40"
        ],
        "correct_output": "B",
        "explanation": "LINQ query expressions (like Select and Where) use deferred execution. The projection is evaluated only when the query is enumerated (by string.Join), reflecting the newly added element 4."
    },
    {
        "id": "pred-string-immutability",
        "topic_id": "arrays-and-spans",
        "title": "String Immutability",
        "code_snippet": """string s = "gotham";
s.ToUpper();
s.Replace("g", "b");

Console.WriteLine(s);""",
        "options": [
            "A) botham",
            "B) GOTHAM",
            "C) BOTHAM",
            "D) gotham"
        ],
        "correct_output": "D",
        "explanation": "Strings in .NET are immutable. Methods like ToUpper() and Replace() return a new string instance without modifying the original string variable 's'."
    },
    {
        "id": "pred-null-coalescing-assignment",
        "topic_id": "operators-and-expressions",
        "title": "Null-Coalescing Assignment (??=)",
        "code_snippet": """string? name = null;
name ??= "Batman";
name ??= "Robin";

Console.WriteLine(name);""",
        "options": [
            "A) null",
            "B) Robin",
            "C) Batman",
            "D) BatmanRobin"
        ],
        "correct_output": "C",
        "explanation": "The '??=' operator assigns the right-hand value only if the left-hand variable is null. Once assigned 'Batman', the second assignment is skipped."
    },
    {
        "id": "pred-record-value-equality",
        "topic_id": "classes-and-objects",
        "title": "Record Value Equality",
        "code_snippet": """public record Hero(string Name, int Level);

var h1 = new Hero("Wayne", 99);
var h2 = new Hero("Wayne", 99);

Console.WriteLine(h1 == h2);""",
        "options": [
            "A) True",
            "B) False",
            "C) Compilation Error",
            "D) NullReferenceException"
        ],
        "correct_output": "A",
        "explanation": "C# records automatically synthesize value-based equality operators. Two record instances with identical member values are considered equal."
    }
]

def generate_predictor_round(count: int = 5) -> Dict[str, Any]:
    """
    Assembles a 60-second speed round of output prediction questions.
    """
    questions = random.sample(CURATED_PREDICTOR_QUESTIONS, min(count, len(CURATED_PREDICTOR_QUESTIONS)))
    round_id = str(uuid.uuid4())[:8]

    return {
        "round_id": round_id,
        "time_limit_seconds": 60,
        "questions": [
            {
                "id": q["id"],
                "topic_id": q["topic_id"],
                "title": q["title"],
                "code_snippet": q["code_snippet"],
                "options": q["options"]
            }
            for q in questions
        ]
    }

def score_predictor_round(answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates speed-round answers, computing accuracy, streak multipliers, and speed bonuses.
    """
    catalog = {q["id"]: q for q in CURATED_PREDICTOR_QUESTIONS}
    correct_count = 0
    current_streak = 0
    max_streak = 0
    total_score = 0
    results = []

    for a in answers:
        q_id = a.get("question_id")
        user_ans = a.get("selected_option", "").strip().upper()
        time_spent = float(a.get("time_spent_seconds", 5.0))

        q = catalog.get(q_id)
        if not q:
            continue

        is_correct = (user_ans == q["correct_output"].upper()) or user_ans.startswith(q["correct_output"].upper())
        if is_correct:
            correct_count += 1
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak

            # Base score: 100 points
            pts = 100
            # Speed bonus: up to 50 extra points if answered in under 5 seconds
            speed_bonus = max(0, int((10.0 - min(time_spent, 10.0)) * 5))
            # Streak bonus: +25 per consecutive correct answer
            streak_bonus = (current_streak - 1) * 25
            total_score += (pts + speed_bonus + streak_bonus)
        else:
            current_streak = 0

        results.append({
            "question_id": q_id,
            "user_answer": user_ans,
            "correct_output": q["correct_output"],
            "is_correct": is_correct,
            "explanation": q["explanation"]
        })

    return {
        "total_score": total_score,
        "correct_count": correct_count,
        "total_questions": len(answers),
        "max_streak": max_streak,
        "streak_bonus": max_streak * 25,
        "speed_bonus": total_score - (correct_count * 100),
        "results": results
    }
