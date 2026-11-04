"""
Bug Hunt Service for CodeCoach
Interactive C# snippet debugging with Zoro/Gotham tactical feedback.
Evaluates clicked lines, detects true bugs, catches false positives, and provides line-by-line fixes.
"""

from typing import Dict, Any, List

# Curated C# Bug Hunt Bank covering real .NET 8/9 edge cases
CURATED_BUG_SCENARIOS = [
    {
        "id": "bug-async-void-crash",
        "title": "Fire-and-Forget Async Hazard",
        "difficulty": "Intermediate",
        "topic_id": "async-and-threading",
        "description": "A payment processing handler crashes the process under unexpected load. Identify the lines causing unhandled exceptions and thread blocking.",
        "code_snippet": """public class PaymentService
{
    private readonly HttpClient _http;

    public PaymentService(HttpClient http)
    {
        _http = http;
    }

    public async void ProcessPaymentAsync(string orderId)
    {
        var response = _http.GetAsync($"/api/pay/{orderId}").Result;
        if (!response.IsSuccessStatusCode)
        {
            throw new PaymentFailedException("Payment rejected");
        }
    }
}""",
        "buggy_lines": [9, 11],
        "explanations": {
            "9": {
                "bug_type": "async void hazard",
                "explanation": "Declaring 'async void' outside of UI event handlers causes unhandled exceptions to crash the CLR process directly because exceptions cannot be caught by callers.",
                "fix_code": "public async Task ProcessPaymentAsync(string orderId)"
            },
            "11": {
                "bug_type": "sync-over-async deadlock risk",
                "explanation": "Calling '.Result' synchronously blocks the executing thread on an asynchronous task, inducing thread-pool starvation and potential deadlocks.",
                "fix_code": "var response = await _http.GetAsync($\"/api/pay/{orderId}\");"
            }
        }
    },
    {
        "id": "bug-closure-loop-capture",
        "title": "Lambda Variable Capture in Loop",
        "difficulty": "Beginner",
        "topic_id": "methods-and-parameters",
        "description": "Scheduled jobs execute using wrong iteration indices. Find where variable scope capture creates identical actions.",
        "code_snippet": """public class JobScheduler
{
    public List<Action> BuildActions(int count)
    {
        var actions = new List<Action>();
        for (int i = 0; i < count; i++)
        {
            actions.Add(() => Console.WriteLine($"Job #{i} executed."));
        }
        return actions;
    }
}""",
        "buggy_lines": [8],
        "explanations": {
            "8": {
                "bug_type": "closure capture bug",
                "explanation": "The lambda closure captures the variable 'i' by reference rather than by value at evaluation time. When actions execute, all print the final loop value.",
                "fix_code": "int current = i;\nactions.Add(() => Console.WriteLine($\"Job #{current} executed.\"));"
            }
        }
    },
    {
        "id": "bug-span-off-by-one",
        "title": "High-Performance Span Slicing Off-by-One",
        "difficulty": "Advanced",
        "topic_id": "arrays-and-spans",
        "description": "Zero-allocation header parser throws IndexOutOfRangeException on packet boundaries.",
        "code_snippet": """public class HeaderParser
{
    public static ReadOnlySpan<char> ExtractToken(ReadOnlySpan<char> header)
    {
        int colonIdx = header.IndexOf(':');
        if (colonIdx == -1) return ReadOnlySpan<char>.Empty;

        return header.Slice(colonIdx + 1, header.Length - colonIdx);
    }
}""",
        "buggy_lines": [8],
        "explanations": {
            "8": {
                "bug_type": "slice length boundary violation",
                "explanation": "Span.Slice(start, length) accepts length, not ending index. Starting at colonIdx + 1 means remaining characters is (header.Length - colonIdx - 1).",
                "fix_code": "return header.Slice(colonIdx + 1, header.Length - colonIdx - 1).Trim();"
            }
        }
    },
    {
        "id": "bug-null-coalescing-linq",
        "title": "Null Dereference in FirstOrDefault",
        "difficulty": "Beginner",
        "topic_id": "operators-and-expressions",
        "description": "User lookup throws System.NullReferenceException when looking up inactive records.",
        "code_snippet": """public class DirectoryService
{
    public string GetPrimaryEmail(List<User> users, int targetId)
    {
        var user = users.FirstOrDefault(u => u.Id == targetId);
        return user.Email.ToLowerInvariant();
    }
}""",
        "buggy_lines": [6],
        "explanations": {
            "6": {
                "bug_type": "unhandled null reference",
                "explanation": "FirstOrDefault returns null if no user matches targetId. Accessing user.Email without null conditional (?.) throws NullReferenceException.",
                "fix_code": "return user?.Email?.ToLowerInvariant() ?? string.Empty;"
            }
        }
    }
]

def get_bug_scenario(scenario_id: str = None) -> Dict[str, Any]:
    """
    Retrieves a bug hunt scenario by ID or returns the first scenario.
    """
    if scenario_id:
        for s in CURATED_BUG_SCENARIOS:
            if s["id"] == scenario_id:
                return s
    return CURATED_BUG_SCENARIOS[0]

def list_bug_scenarios() -> List[Dict[str, Any]]:
    """
    Lists all available bug hunt scenarios without revealing buggy line numbers.
    """
    return [
        {
            "id": s["id"],
            "title": s["title"],
            "difficulty": s["difficulty"],
            "topic_id": s["topic_id"],
            "description": s["description"],
            "code_snippet": s["code_snippet"],
            "total_bugs": len(s["buggy_lines"])
        }
        for s in CURATED_BUG_SCENARIOS
    ]

def evaluate_bug_hunt_submission(scenario_id: str, selected_lines: List[int]) -> Dict[str, Any]:
    """
    Grades user line selections against the actual bug locations.
    Returns detected bugs, missed bugs, and false positives with Zoro-style tactical explanations.
    """
    scenario = get_bug_scenario(scenario_id)
    actual_buggy = set(scenario["buggy_lines"])
    user_selected = set(selected_lines)

    found = actual_buggy.intersection(user_selected)
    missed = actual_buggy.difference(user_selected)
    false_positives = user_selected.difference(actual_buggy)

    total_bugs = len(actual_buggy)
    found_count = len(found)
    score = round((found_count / total_bugs) * 100, 1) if total_bugs > 0 else 100.0

    detected_bugs = []
    explanations_dict = scenario["explanations"]
    for line in sorted(found):
        line_str = str(line)
        detail = explanations_dict.get(line_str, {
            "bug_type": "Critical C# Defect",
            "explanation": "A structural or logic error was detected at this line.",
            "fix_code": "// Review line logic"
        })
        detected_bugs.append({
            "line": line,
            "bug_type": detail["bug_type"],
            "explanation": detail["explanation"],
            "fix_code": detail["fix_code"]
        })

    all_found = (found_count == total_bugs) and (len(false_positives) == 0)

    if all_found:
        feedback = "⚔️ Flawless Observation! All defects eliminated with zero false alarms."
    elif found_count > 0 and len(false_positives) > 0:
        feedback = f"Identified {found_count} of {total_bugs} bugs, but marked {len(false_positives)} healthy line(s)."
    elif found_count > 0:
        feedback = f"Identified {found_count} of {total_bugs} bugs. {len(missed)} defect(s) remain hidden."
    else:
        feedback = "No actual bugs found in selected lines. Inspect nullability and thread safety."

    return {
        "scenario_id": scenario_id,
        "score": score,
        "found_count": found_count,
        "total_bugs": total_bugs,
        "all_found": all_found,
        "feedback": feedback,
        "detected_bugs": detected_bugs,
        "missed_lines": sorted(list(missed)),
        "false_positives": sorted(list(false_positives))
    }
