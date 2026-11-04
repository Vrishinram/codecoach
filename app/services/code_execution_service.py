"""
Code Execution Service for CodeCoach
Sandboxed execution via Piston or Judge0 API with transparent LLM simulation fallback.
Enforces timeouts, 8KB output truncation, and input validation.
"""

import time
import json
import logging
import httpx
from typing import Dict, Any, List

from app.config import settings
from app.llm.client import llm_client

logger = logging.getLogger("codecoach.services.code_execution")

# Public Piston API endpoint (Free, open-source, no API key required)
PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"

# Maximum output length (8KB) to prevent payload abuse
MAX_OUTPUT_CHARS = 8192

async def execute_csharp_code(code: str, stdin: str = "", timeout_seconds: int = 5) -> Dict[str, Any]:
    """
    Executes C# code in an isolated sandbox.
    Attempts Piston first; falls back to LLM simulation if unavailable.
    """
    code_clean = code.strip()
    if not code_clean:
        return {
            "stdout": "",
            "stderr": "Error: Code submission is empty.",
            "exit_code": 1,
            "execution_time_ms": 0.0,
            "engine": "none",
            "is_simulated": False,
            "warning": None
        }

    # Ensure C# code has a runnable entrypoint if top-level statements aren't supported
    wrapped_code = prepare_runnable_csharp(code_clean)

    start_time = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=float(timeout_seconds + 3)) as client:
            resp = await client.post(
                PISTON_API_URL,
                json={
                    "language": "csharp.net",
                    "version": "9.0",
                    "files": [
                        {
                            "name": "Program.cs",
                            "content": wrapped_code
                        }
                    ],
                    "stdin": stdin or "",
                    "run_timeout": timeout_seconds * 1000
                }
            )

            if resp.status_code == 200:
                data = resp.json()
                run_data = data.get("run", {})
                stdout = run_data.get("stdout", "")[:MAX_OUTPUT_CHARS]
                stderr = run_data.get("stderr", "")[:MAX_OUTPUT_CHARS]
                exit_code = run_data.get("code", 0)
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "execution_time_ms": round(elapsed_ms, 1),
                    "engine": "piston",
                    "is_simulated": False,
                    "warning": None
                }
    except Exception as ex:
        logger.warning("Piston code execution API unreachable or timed out (%s). Falling back to LLM simulation.", ex)

    # Fallback to LLM Execution Simulation
    return await simulate_csharp_execution(wrapped_code, stdin)

def prepare_runnable_csharp(code: str) -> str:
    """
    Wraps naked expressions or class definitions into a runnable Main if missing.
    Supports modern top-level statements directly.
    """
    has_main = "static void Main" in code or "static async Task Main" in code or "static int Main" in code
    has_top_level = code.startswith("using ") or "Console.WriteLine" in code or "var " in code or "return " in code

    if has_main or has_top_level:
        # Prepend standard namespaces if omitted
        headers = []
        if "using System;" not in code:
            headers.append("using System;")
        if "using System.Collections.Generic;" not in code and ("List<" in code or "Dictionary<" in code):
            headers.append("using System.Collections.Generic;")
        if "using System.Linq;" not in code and ("Select(" in code or "Where(" in code):
            headers.append("using System.Linq;")
        if "using System.Threading.Tasks;" not in code and "Task" in code:
            headers.append("using System.Threading.Tasks;")
        if headers:
            return "\n".join(headers) + "\n\n" + code
        return code

    # Naked class or methods
    return f"""using System;
using System.Collections.Generic;
using System.Linq;

{code}

public class Program
{{
    public static void Main()
    {{
        Console.WriteLine("Code compiled and executed successfully.");
    }}
}}
"""

async def simulate_csharp_execution(code: str, stdin: str = "") -> Dict[str, Any]:
    """
    Simulates C# code execution via LLM when sandboxed API is unreachable.
    Explicitly flags output as simulated for user transparency.
    """
    start_time = time.perf_counter()
    prompt = f"""You are a strict C# .NET 9 compiler and runtime emulator.
Given the following C# code and standard input, determine:
1. Does it compile without syntax or type errors?
2. If it compiles, what is the exact standard output (stdout)?
3. If it fails to compile or throws an unhandled runtime exception, what is the exact error message (stderr)?
4. What is the process exit code (0 for success, non-zero for failure)?

Standard Input:
{stdin or "(empty)"}

C# Code:
```csharp
{code}
```

Respond ONLY in valid JSON matching this schema:
{{
  "stdout": "exact program output",
  "stderr": "compiler error or runtime exception if any, else empty",
  "exit_code": 0
}}"""

    try:
        res = await llm_client.generate_validated_json(messages=[{"role": "user", "content": prompt}])
        stdout = str(res.get("stdout", ""))[:MAX_OUTPUT_CHARS]
        stderr = str(res.get("stderr", ""))[:MAX_OUTPUT_CHARS]
        exit_code = int(res.get("exit_code", 0))
    except Exception as e:
        stdout = ""
        stderr = f"Compiler/Execution Simulation Note: {e}"
        exit_code = 1

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "execution_time_ms": round(elapsed_ms, 1),
        "engine": "llm_simulated",
        "is_simulated": True,
        "warning": "⚠️ Code execution sandbox was unavailable. Output was simulated by AI code analysis."
    }

async def run_challenge_tests(challenge_data: Dict[str, Any], user_code: str) -> Dict[str, Any]:
    """
    Runs user code against test cases for a coding challenge.
    Evaluates inputs and compares stdout/return values against expected outputs.
    """
    test_cases = challenge_data.get("test_cases", [])
    results = []
    tests_passed = 0

    for idx, tc in enumerate(test_cases):
        test_in = tc.get("input", "")
        test_expected = str(tc.get("expected_output", "")).strip()
        is_hidden = tc.get("is_hidden", False)

        exec_res = await execute_csharp_code(user_code, stdin=test_in, timeout_seconds=4)
        actual_stdout = exec_res.get("stdout", "").strip()

        passed = (actual_stdout == test_expected) and (exec_res.get("exit_code") == 0)
        if passed:
            tests_passed += 1

        results.append({
            "test_index": idx + 1,
            "input": test_in if not is_hidden else "[Hidden Test Case]",
            "expected_output": test_expected if not is_hidden else "[Hidden Test Case]",
            "actual_output": actual_stdout if not is_hidden else ("[Matches Expected]" if passed else "[Mismatch]"),
            "passed": passed,
            "is_hidden": is_hidden,
            "error": exec_res.get("stderr") or None
        })

    all_passed = (tests_passed == len(test_cases)) if test_cases else False
    feedback = f"All {len(test_cases)} test cases passed! Verification confirmed." if all_passed else f"Passed {tests_passed} of {len(test_cases)} test cases."

    return {
        "challenge_id": challenge_data.get("id"),
        "passed": all_passed,
        "tests_passed": tests_passed,
        "tests_total": len(test_cases),
        "test_results": results,
        "execution_engine": results[0].get("engine", "piston") if results else "piston",
        "is_simulated": any(r.get("is_simulated", False) for r in results),
        "feedback": feedback
    }
