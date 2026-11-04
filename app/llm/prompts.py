from app.config import settings

def get_educator_system_prompt() -> str:
    return f"""You are {settings.ASSISTANT_NAME}, an elite senior software engineer and principal C# / .NET instructor.
Your teaching style is clean, modern, highly encouraging, authoritative, and deeply practical.
You adhere strictly to modern C# (C# 10, 11, 12, 13) and modern .NET (.NET 8 and .NET 9 LTS).
You NEVER use anime, childish, or gimmick character themes. Keep explanations crisp, professional, elegant, and packed with real-world production insights.

Guidelines for formatting your C# code and explanations:
1. Always format C# code blocks cleanly with ```csharp ... ```.
2. Highlight standard idioms, best practices, memory allocation, and performance tips where appropriate.
3. Be concise and pedagogical. When asked a question, provide direct answers followed by a minimal illustrative code example.
4. When a user sends slash commands (/start, /next, /hint, /skip, /explain, /progress, /links, /videos, /review), give them exact instruction on how the training system works or directly guide their current step.
"""

def get_quiz_generation_prompt(
    topic_title: str,
    subtopics: list,
    set_size: int = 25,
    weak_subtopics: list = None,
    excluded_prompts: list = None
) -> str:
    focus_note = ""
    if weak_subtopics:
        focus_note = f"\nFOCUS AREA: The student struggled with these specific subtopics: {', '.join(weak_subtopics)}. Allocate more questions to reinforce these areas.\n"

    excluded_note = ""
    if excluded_prompts:
        preview = [p[:60] for p in excluded_prompts[-15:]]
        excluded_note = f"\nDO NOT repeat or generate questions similar to these existing ones:\n- " + "\n- ".join(preview)

    return f"""You are generating an official C# / .NET training set of exactly {set_size} Multiple Choice Questions (MCQs) for the topic: "{topic_title}".
Subtopics in this topic: {', '.join(subtopics)}.{focus_note}{excluded_note}

ALL {set_size} questions MUST be Multiple Choice Questions ("mcq"), each having exactly 4 distinct options labeled A), B), C), and D).
Incorporate a rich variety of styles across the set:
- Conceptual & Architectural MCQs (core principles, memory allocation, idioms)
- Output Prediction MCQs (provide a concise C# code snippet and 4 potential outputs as options)
- Fill-in-the-Blank MCQs (provide a C# snippet with `___` and 4 code tokens as options)
- Bug Hunting & Best Practice MCQs (identify the bug, memory leak, or optimal idiom among 4 choices)

Conciseness & Formatting Guidelines:
- Keep prompts direct and focused.
- Code snippets should be under 6 lines of clean C#.
- Explanations must be concise (1 to 2 sentences max).
- 'question_type' must be "mcq" for every question.
- 'options' must be a list of 4 distinct strings: ["A) ...", "B) ...", "C) ...", "D) ..."].
- 'correct_answer' must be the exact letter ("A", "B", "C", or "D").

Difficulty Ramp:
- Questions 1 to 5: Difficulty 1 (Foundational syntax & principles)
- Questions 6 to 12: Difficulty 2 (Standard usage & common patterns)
- Questions 13 to 18: Difficulty 3 (Edge cases, collections & intermediate logic)
- Questions 19 to 22: Difficulty 4 (Tricky pitfalls, performance & threading)
- Questions 23 to {set_size}: Difficulty 5 (Advanced real-world architecture & internal runtime mechanics)

Format your output strictly as a JSON list of {set_size} question objects with these exact keys:
[
  {{
    "question_index": 1,
    "question_type": "mcq",
    "subtopic": "name of subtopic",
    "difficulty": 1,
    "prompt": "Clear, precise question text",
    "code_snippet": "Optional C# snippet or null",
    "options": ["A) option 1", "B) option 2", "C) option 3", "D) option 4"],
    "correct_answer": "A",
    "explanation": "Brief 1-2 sentence explanation of why A is correct.",
    "hint": "Gentle nudge without revealing the exact answer"
  }}
]
"""

def get_teach_back_grading_prompt(topic_title: str, subtopics: list, student_explanation: str) -> str:
    return f"""You are evaluating a student's teach-back explanation for the C# / .NET topic: "{topic_title}".
Subtopics covered: {', '.join(subtopics)}.

Student's Explanation:
\"\"\"{student_explanation}\"\"\"

Grade the explanation strictly based on these three rubric pillars (0 to 100 each):
1. Accuracy: Are the technical concepts, terminology, and C# runtime behaviors stated correctly?
2. Completeness: Did the student capture the core essence and primary use cases of the topic?
3. Clarity: Is the explanation well-structured, coherent, and articulated in the student's own words?

Overall score = (Accuracy * 0.4) + (Completeness * 0.4) + (Clarity * 0.2).
Passing threshold is {settings.PASS_SCORE}.

Return strictly valid JSON with this exact schema:
{{
  "accuracy_score": 85.0,
  "completeness_score": 80.0,
  "clarity_score": 90.0,
  "overall_score": 84.0,
  "passed": true,
  "missing_points": ["List 1 to 3 key technical points or nuances the student omitted, if any"],
  "feedback": "Constructive, encouraging 2-3 sentence educator feedback on what was strong and what to remember."
}}
"""

def get_app_challenge_generation_prompt(topic_title: str, subtopics: list) -> str:
    return f"""Create a single, highly practical, small C# coding challenge to verify a student's real-world mastery of "{topic_title}".
Subtopics: {', '.join(subtopics)}.

The challenge should take 5-15 lines of C# code to solve, testing both correctness and idiomatic C# conventions.

Return strictly valid JSON with this exact schema:
{{
  "topic_id": "{topic_title}",
  "prompt": "Clear problem statement describing the function or class to implement, including parameter specifications and expected behavior.",
  "starter_code": "public class Solution \\n{{\\n    // Write your code here\\n}}"
}}
"""

def get_app_challenge_review_prompt(topic_title: str, problem_prompt: str, student_code: str) -> str:
    return f"""You are a principal C# engineer doing a code review on a student's submission.
Topic: "{topic_title}"
Problem Statement:
{problem_prompt}

Student's Submitted C# Code:
\"\"\"{student_code}\"\"\"

Review the code for:
1. Correctness: Does it solve the problem without runtime exceptions or bugs?
2. Edge cases: Does it handle nulls, empty collections, boundary values?
3. Modern C# Style: Clean syntax, proper naming conventions (PascalCase, camelCase), idiomatic patterns, no redundant allocations.

Give an overall score from 0 to 100.
Passing score is {settings.PASS_SCORE}.

Return strictly valid JSON with this exact schema:
{{
  "score": 90.0,
  "passed": true,
  "correctness_notes": "Assessment of functional correctness",
  "edge_case_notes": "Assessment of edge cases handled or overlooked",
  "style_notes": "Assessment of C# idioms, clean architecture, and readability",
  "feedback": "Concise summary review pointing out highlights and areas for improvement."
}}
"""

def get_placement_test_generation_prompt() -> str:
    return """Generate a 10-question C# and .NET placement test covering beginner to advanced levels:
- Questions 1-2: C# Basics (types, operators, loops)
- Questions 3-4: Object-Oriented Programming (inheritance, interfaces, records)
- Questions 5-6: Intermediate C# (LINQ, delegates, async/await)
- Questions 7-8: .NET & ASP.NET Core (DI lifetimes, middleware, REST APIs)
- Questions 9-10: Advanced .NET (EF Core, JWT, clean architecture, SOLID)

Return strictly valid JSON with a list of 10 questions with this exact structure:
[
  {
    "id": 1,
    "topic_id": "variables-and-types",
    "level_id": "csharp-basics",
    "prompt": "Question text here",
    "code_snippet": "Optional C# snippet or null",
    "options": ["A) option 1", "B) option 2", "C) option 3", "D) option 4"],
    "correct_option_index": 0
  }
]
"""

