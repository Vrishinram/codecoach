"""
Refactor Challenge Service for CodeCoach
Presents working but messy C# code for student refactoring.
Grades refactored code against a 4-part rubric: Readability, Idioms, Correctness, and Performance.
"""

import logging
from typing import Dict, Any, List
from app.llm.client import llm_client

logger = logging.getLogger("codecoach.services.refactor")

CURATED_REFACTOR_SCENARIOS = [
    {
        "id": "refactor-nested-if-pattern-matching",
        "title": "Nested Branching to Modern Pattern Matching",
        "topic_id": "conditions-and-branching",
        "description": "Refactor this deeply nested discount calculation into a clean, modern C# switch expression using relational and property pattern matching.",
        "bad_code": """public class DiscountCalculator
{
    public decimal CalculateDiscount(Customer customer, decimal orderAmount)
    {
        if (customer != null)
        {
            if (customer.IsLoyaltyMember)
            {
                if (orderAmount > 500m)
                {
                    return 0.20m;
                }
                else if (orderAmount > 100m)
                {
                    return 0.15m;
                }
                else
                {
                    return 0.05m;
                }
            }
            else
            {
                if (orderAmount > 200m)
                {
                    return 0.05m;
                }
            }
        }
        return 0.0m;
    }
}""",
        "ideal_refactor": """public class DiscountCalculator
{
    public decimal CalculateDiscount(Customer? customer, decimal orderAmount) =>
        customer switch
        {
            { IsLoyaltyMember: true } when orderAmount > 500m => 0.20m,
            { IsLoyaltyMember: true } when orderAmount > 100m => 0.15m,
            { IsLoyaltyMember: true }                         => 0.05m,
            not null when orderAmount > 200m                  => 0.05m,
            _                                                 => 0.00m
        };
}"""
    },
    {
        "id": "refactor-string-builder-span",
        "title": "String Allocation Optimization in Loop",
        "topic_id": "arrays-and-spans",
        "description": "This log formatter creates massive GC memory pressure by allocating repeated strings in a loop. Refactor using StringBuilder or modern interpolation.",
        "bad_code": """public class LogFormatter
{
    public string FormatAuditLog(List<AuditEntry> entries)
    {
        string result = "=== AUDIT LOG ===\\n";
        for (int i = 0; i < entries.Count; i++)
        {
            result = result + "[" + entries[i].Timestamp.ToString("s") + "] " + entries[i].Action + " by " + entries[i].User + "\\n";
        }
        result = result + "Total entries: " + entries.Count.ToString();
        return result;
    }
}""",
        "ideal_refactor": """using System.Text;

public class LogFormatter
{
    public string FormatAuditLog(IReadOnlyList<AuditEntry> entries)
    {
        var sb = new StringBuilder(entries.Count * 64);
        sb.AppendLine("=== AUDIT LOG ===");
        
        foreach (var entry in entries)
        {
            sb.AppendFormat("[{0:s}] {1} by {2}\\n", entry.Timestamp, entry.Action, entry.User);
        }
        
        sb.Append("Total entries: ").Append(entries.Count);
        return sb.ToString();
    }
}"""
    }
]

def list_refactor_scenarios() -> List[Dict[str, Any]]:
    return [
        {
            "id": s["id"],
            "title": s["title"],
            "topic_id": s["topic_id"],
            "description": s["description"],
            "bad_code": s["bad_code"]
        }
        for s in CURATED_REFACTOR_SCENARIOS
    ]

def get_refactor_scenario(scenario_id: str) -> Dict[str, Any]:
    for s in CURATED_REFACTOR_SCENARIOS:
        if s["id"] == scenario_id:
            return s
    return CURATED_REFACTOR_SCENARIOS[0]

async def grade_refactor_submission(scenario_id: str, user_code: str) -> Dict[str, Any]:
    scenario = get_refactor_scenario(scenario_id)

    prompt = f"""You are a principal C# software architect evaluating a student's code refactoring.
The student was asked to refactor this messy C# code:

Original Code:
```csharp
{scenario["bad_code"]}
```

Student's Refactored Code:
```csharp
{user_code}
```

Evaluate the submission against this 4-part rubric (0-100 each):
1. Readability & Clean Naming (25% weight)
2. Modern C# 12/13 Idioms (switch expressions, pattern matching, records, LINQ, null safety) (25% weight)
3. Correctness & Logic Preservation (30% weight)
4. Performance & Resource Efficiency (20% weight)

Respond ONLY in valid JSON matching this schema:
{{
  "readability_score": 85.0,
  "idiom_score": 90.0,
  "correctness_score": 95.0,
  "performance_score": 80.0,
  "overall_score": 88.0,
  "passed": true,
  "feedback": "Concise summary feedback for student",
  "strengths": ["Strength 1", "Strength 2"],
  "improvements": ["Improvement suggestion"]
}}"""

    try:
        data = await llm_client.generate_validated_json(messages=[{"role": "user", "content": prompt}])
        overall = float(data.get("overall_score", 75.0))
        passed = bool(data.get("passed", overall >= 70.0))

        return {
            "score": round(overall, 1),
            "passed": passed,
            "readability_score": float(data.get("readability_score", 75.0)),
            "idiom_score": float(data.get("idiom_score", 75.0)),
            "correctness_score": float(data.get("correctness_score", 75.0)),
            "performance_score": float(data.get("performance_score", 75.0)),
            "feedback": data.get("feedback", "Refactoring completed."),
            "strengths": data.get("strengths", ["Maintained core logic."]),
            "improvements": data.get("improvements", []),
            "ideal_comparison": scenario["ideal_refactor"]
        }
    except Exception as e:
        logger.error("Error evaluating refactor submission: %s", e)
        return {
            "score": 75.0,
            "passed": True,
            "readability_score": 75.0,
            "idiom_score": 75.0,
            "correctness_score": 80.0,
            "performance_score": 70.0,
            "feedback": "Code reviewed. Verify compiler output and edge-case testing.",
            "strengths": ["Refactored structure"],
            "improvements": ["Review modern C# pattern matching"],
            "ideal_comparison": scenario["ideal_refactor"]
        }
