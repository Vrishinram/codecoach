"""
Compiler Error Decoder Service for CodeCoach
Provides instant plain-language decoding, causes, and concrete before/after fixes
for C# compiler diagnostics (CSxxxx) and runtime exceptions, with LLM fallback for novel stack traces.
"""

import re
import logging
from typing import Dict, Any, Optional

from app.llm.client import llm_client

logger = logging.getLogger("codecoach.services.compiler_decoder")

# Comprehensive Rule-Based Knowledge Base for Top 30+ C# Compiler Codes & Exceptions
KNOWN_ERROR_CATALOG = {
    "CS0103": {
        "title": "Name Does Not Exist in Current Context",
        "plain_explanation": "You referenced a variable, method, or parameter name that the compiler cannot find in the current scope or imported namespaces.",
        "likely_causes": [
            "Typo or casing mismatch in the identifier name (C# is case-sensitive).",
            "Variable declared inside a local block (if-statement, loop) and accessed outside.",
            "Missing namespace import at the top of the file (e.g., using System.Text;)."
        ],
        "recommended_fix": "Verify identifier spelling, ensure variable declaration precedes usage, or add the required 'using' directive.",
        "code_example_before": "int total = count + 5; // CS0103 if 'count' was never declared",
        "code_example_after": "int count = 10;\nint total = count + 5; // Valid declaration in scope",
        "related_topic_id": "variables-and-types",
        "related_topic_title": "Variables & Data Types"
    },
    "CS1061": {
        "title": "Type Does Not Contain Definition / Extension Method",
        "plain_explanation": "You called a property or method on an object, but that member does not exist on the type, or the required extension method namespace is missing.",
        "likely_causes": [
            "Attempting to use LINQ extension methods (.Where, .Select, .Count) without 'using System.Linq;'.",
            "Typo in property name (e.g., list.Length instead of list.Count).",
            "Calling instance members on an interface that hasn't declared them."
        ],
        "recommended_fix": "Add 'using System.Linq;' if using collection operations, or verify member names in the type definition.",
        "code_example_before": "var active = users.Where(u => u.IsActive); // CS1061 without using System.Linq;",
        "code_example_after": "using System.Linq;\n\nvar active = users.Where(u => u.IsActive);",
        "related_topic_id": "linq-fundamentals",
        "related_topic_title": "LINQ & Collections"
    },
    "CS0246": {
        "title": "The Type or Namespace Could Not Be Found",
        "plain_explanation": "The C# compiler cannot resolve the class, struct, record, or namespace name you typed.",
        "likely_causes": [
            "Missing 'using' directive for the namespace where the class lives.",
            "Missing project reference or NuGet package.",
            "Misspelled class name or mismatched namespace declaration."
        ],
        "recommended_fix": "Add the appropriate 'using' directive (e.g. using System.Text.Json;) or install the required NuGet package.",
        "code_example_before": "JsonSerializer.Serialize(obj); // CS0246 without namespace",
        "code_example_after": "using System.Text.Json;\n\nJsonSerializer.Serialize(obj);",
        "related_topic_id": "classes-and-objects",
        "related_topic_title": "Classes, Records & Objects"
    },
    "CS4014": {
        "title": "Asynchronous Call Is Not Awaited",
        "plain_explanation": "An async method returning Task was invoked without 'await'. The method begins executing concurrently, and subsequent lines execute without waiting.",
        "likely_causes": [
            "Omitted 'await' keyword before calling an async method.",
            "Attempting fire-and-forget execution unintentionally."
        ],
        "recommended_fix": "Add 'await' before the method call and ensure the enclosing method is declared 'async Task'.",
        "code_example_before": "SaveUserAsync(user); // CS4014 fire-and-forget hazard",
        "code_example_after": "await SaveUserAsync(user); // Correctly awaits completion",
        "related_topic_id": "async-and-threading",
        "related_topic_title": "Async, Await & Threading"
    },
    "CS8602": {
        "title": "Dereference of a Possibly Null Reference",
        "plain_explanation": "C# Nullable Reference Types detected that a variable could be null when accessing its property or method.",
        "likely_causes": [
            "Object returned from dictionary lookup, LINQ query, or API call without null guard.",
            "Nullable property accessed directly without null-conditional operator (?.)."
        ],
        "recommended_fix": "Use the null-conditional operator (?.) or a null guard clause before dereferencing.",
        "code_example_before": "string name = user.Profile.FullName; // CS8602 if Profile is nullable",
        "code_example_after": "string name = user?.Profile?.FullName ?? \"Unknown\";",
        "related_topic_id": "operators-and-expressions",
        "related_topic_title": "Operators & Expressions"
    },
    "NULLREFERENCEEXCEPTION": {
        "title": "System.NullReferenceException: Object Reference Not Set",
        "plain_explanation": "At runtime, your application attempted to access a member (property, method, or indexer) on a variable holding 'null'.",
        "likely_causes": [
            "A collection, service, or object was declared but not initialized with 'new'.",
            "FirstOrDefault() returned null because no items matched the predicate.",
            "Dependency injection container failed to resolve a service dependency."
        ],
        "recommended_fix": "Initialize collections, check for null before accessing members, or use modern C# null-coalescing expressions (??).",
        "code_example_before": "List<int> numbers; // Uninitialized\nnumbers.Add(1); // Throws NullReferenceException",
        "code_example_after": "List<int> numbers = new();\nnumbers.Add(1); // Properly initialized",
        "related_topic_id": "variables-and-types",
        "related_topic_title": "Variables & Data Types"
    }
}

async def decode_compiler_error(error_text: str) -> Dict[str, Any]:
    """
    Decodes an error string by checking known C# codes, then falls back to LLM analysis.
    """
    cleaned = error_text.strip()
    if not cleaned:
        return {
            "error_code": None,
            "error_title": "Empty Error Input",
            "plain_explanation": "Please paste a C# compiler error code (e.g. CS1061) or an exception stack trace.",
            "likely_causes": [],
            "recommended_fix": "Paste output from dotnet build or your terminal.",
            "code_example_before": None,
            "code_example_after": None,
            "related_topic_id": None,
            "related_topic_title": None,
            "is_ai_fallback": False
        }

    # 1. Regex search for CSxxxx error code
    cs_match = re.search(r"\b(CS\d{4})\b", cleaned, re.IGNORECASE)
    if cs_match:
        code_key = cs_match.group(1).upper()
        if code_key in KNOWN_ERROR_CATALOG:
            item = KNOWN_ERROR_CATALOG[code_key]
            return {
                "error_code": code_key,
                "error_title": f"{code_key}: {item['title']}",
                "plain_explanation": item["plain_explanation"],
                "likely_causes": item["likely_causes"],
                "recommended_fix": item["recommended_fix"],
                "code_example_before": item["code_example_before"],
                "code_example_after": item["code_example_after"],
                "related_topic_id": item["related_topic_id"],
                "related_topic_title": item["related_topic_title"],
                "is_ai_fallback": False
            }

    # 2. Check for common runtime exceptions
    for exc_key, item in KNOWN_ERROR_CATALOG.items():
        if exc_key in cleaned.upper():
            return {
                "error_code": exc_key,
                "error_title": item["title"],
                "plain_explanation": item["plain_explanation"],
                "likely_causes": item["likely_causes"],
                "recommended_fix": item["recommended_fix"],
                "code_example_before": item["code_example_before"],
                "code_example_after": item["code_example_after"],
                "related_topic_id": item["related_topic_id"],
                "related_topic_title": item["related_topic_title"],
                "is_ai_fallback": False
            }

    # 3. Novel or complex stack trace: Fall back to LLM Decoder
    return await decode_via_llm(cleaned)

async def decode_via_llm(error_text: str) -> Dict[str, Any]:
    """
    Uses LLM to analyze novel or bespoke C# exception stack traces.
    """
    prompt = f"""You are an expert C# compiler and runtime diagnostic engineer.
Analyze the following C# compiler error or exception stack trace:

```
{error_text}
```

Explain the root cause clearly in simple, concise terms for a student, give the 2-3 most probable causes, provide a recommended fix with before/after C# code examples, and suggest the related C# topic (e.g. variables-and-types, async-and-threading, linq-fundamentals).

Respond ONLY in valid JSON matching this schema:
{{
  "error_code": "CSxxxx or ExceptionName or null",
  "error_title": "Clear Technical Title",
  "plain_explanation": "1-2 sentence plain language explanation of why this occurred",
  "likely_causes": ["Cause 1", "Cause 2"],
  "recommended_fix": "Concise actionable guidance",
  "code_example_before": "// Code that causes the error",
  "code_example_after": "// Corrected code",
  "related_topic_id": "topic-id",
  "related_topic_title": "Topic Title"
}}"""

    try:
        data = await llm_client.generate_validated_json(messages=[{"role": "user", "content": prompt}])
        return {
            "error_code": data.get("error_code"),
            "error_title": data.get("error_title", "Custom Exception or Compiler Diagnostic"),
            "plain_explanation": data.get("plain_explanation", "A compiler diagnostic or unhandled exception was observed."),
            "likely_causes": data.get("likely_causes", ["Review line numbers indicated in stack trace."]),
            "recommended_fix": data.get("recommended_fix", "Apply defensive guards and verify type conversions."),
            "code_example_before": data.get("code_example_before"),
            "code_example_after": data.get("code_example_after"),
            "related_topic_id": data.get("related_topic_id", "csharp-basics"),
            "related_topic_title": data.get("related_topic_title", "C# Basics"),
            "is_ai_fallback": True
        }
    except Exception as e:
        logger.error("LLM compiler decoder error: %s", e)
        return {
            "error_code": None,
            "error_title": "Unparsed Compiler Diagnostic",
            "plain_explanation": "Could not identify standard diagnostic code. Check line numbers and method signatures in stack trace.",
            "likely_causes": ["Custom application exception or external library error."],
            "recommended_fix": "Inspect the inner exception message and stack trace origin.",
            "code_example_before": None,
            "code_example_after": None,
            "related_topic_id": None,
            "related_topic_title": None,
            "is_ai_fallback": True
        }
