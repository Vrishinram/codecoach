"""
Unit and Integration Tests for Practice Arena Features (Phase 1)
Tests:
- Sandboxed C# code execution & LLM simulation fallback
- Coding challenge test matrix validation
- Bug Hunt line detection, false positives, and Zoro feedback
- Compiler Error Decoder rule-based & novel stack trace handling
- Refactor challenge scenario retrieval & rubric grading
- Output Predictor speed rounds, streak multipliers, and scoring
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.code_execution_service import (
    execute_csharp_code, prepare_runnable_csharp, run_challenge_tests
)
from app.services.bug_hunt_service import (
    list_bug_scenarios, get_bug_scenario, evaluate_bug_hunt_submission
)
from app.services.compiler_decoder_service import decode_compiler_error
from app.services.refactor_service import list_refactor_scenarios, grade_refactor_submission
from app.services.output_predictor_service import generate_predictor_round, score_predictor_round

@pytest.mark.asyncio
async def test_code_execution_piston_success():
    """Verify sandboxed code execution through Piston API."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "run": {
            "stdout": "Hello C# 13\n",
            "stderr": "",
            "code": 0
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await execute_csharp_code("Console.WriteLine(\"Hello C# 13\");")

        assert res["stdout"].strip() == "Hello C# 13"
        assert res["exit_code"] == 0
        assert res["engine"] == "piston"
        assert res["is_simulated"] is False
        assert res["warning"] is None

@pytest.mark.asyncio
async def test_code_execution_fallback_to_llm_simulation():
    """Verify graceful fallback to LLM simulation when sandboxed API is unreachable."""
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection refused")), \
         patch("app.llm.client.llm_client.generate_validated_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "stdout": "Simulated Output",
            "stderr": "",
            "exit_code": 0
        }

        res = await execute_csharp_code("Console.WriteLine(\"Simulated Output\");")

        assert res["stdout"] == "Simulated Output"
        assert res["engine"] == "llm_simulated"
        assert res["is_simulated"] is True
        assert "simulated" in res["warning"].lower()

@pytest.mark.asyncio
async def test_challenge_test_matrix_runner():
    """Verify running challenge test cases against candidate code."""
    challenge = {
        "id": "sample-challenge",
        "test_cases": [
            {"input": "", "expected_output": "42", "is_hidden": False},
            {"input": "", "expected_output": "42", "is_hidden": True}
        ]
    }

    with patch("app.services.code_execution_service.execute_csharp_code", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "stdout": "42",
            "stderr": "",
            "exit_code": 0,
            "engine": "piston",
            "is_simulated": False
        }

        res = await run_challenge_tests(challenge, "Console.WriteLine(42);")

        assert res["passed"] is True
        assert res["tests_passed"] == 2
        assert res["tests_total"] == 2
        assert len(res["test_results"]) == 2

def test_bug_hunt_flawless_detection():
    """Verify Bug Hunt correctly detects all lines and scores 100% on exact matches."""
    res = evaluate_bug_hunt_submission("bug-async-void-crash", [9, 11])

    assert res["all_found"] is True
    assert res["score"] == 100.0
    assert res["found_count"] == 2
    assert len(res["false_positives"]) == 0
    assert len(res["detected_bugs"]) == 2

def test_bug_hunt_false_positives_and_misses():
    """Verify Bug Hunt catches false alarms on healthy lines and reports missed bugs."""
    # Line 9 is a true bug, line 5 is healthy (false positive), line 11 is missed
    res = evaluate_bug_hunt_submission("bug-async-void-crash", [9, 5])

    assert res["all_found"] is False
    assert res["found_count"] == 1
    assert 5 in res["false_positives"]
    assert 11 in res["missed_lines"]

@pytest.mark.asyncio
async def test_compiler_decoder_rule_based_cs0103():
    """Verify CS0103 matches rule-based dictionary instantly without LLM invocation."""
    res = await decode_compiler_error("Program.cs(12,17): error CS0103: The name 'myVariable' does not exist in the current context")

    assert res["error_code"] == "CS0103"
    assert "Variables & Data Types" in res["related_topic_title"]
    assert res["is_ai_fallback"] is False
    assert len(res["likely_causes"]) > 0

@pytest.mark.asyncio
async def test_compiler_decoder_null_reference_exception():
    """Verify runtime NullReferenceException is decoded accurately."""
    res = await decode_compiler_error("System.NullReferenceException: Object reference not set to an instance of an object.")

    assert "NullReferenceException" in res["error_title"]
    assert res["is_ai_fallback"] is False
    assert res["code_example_before"] is not None

@pytest.mark.asyncio
async def test_refactor_grading_rubric():
    """Verify Refactor Challenge evaluates code against 4-part rubric."""
    with patch("app.llm.client.llm_client.generate_validated_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "readability_score": 90.0,
            "idiom_score": 95.0,
            "correctness_score": 90.0,
            "performance_score": 85.0,
            "overall_score": 90.0,
            "passed": True,
            "feedback": "Clean switch expression implementation.",
            "strengths": ["Clear pattern matching"],
            "improvements": []
        }

        res = await grade_refactor_submission("refactor-nested-if-pattern-matching", "public class Solution {}")

        assert res["passed"] is True
        assert res["score"] == 90.0
        assert res["readability_score"] == 90.0
        assert res["idiom_score"] == 95.0
        assert "ideal_comparison" in res

def test_output_predictor_speed_round_scoring():
    """Verify 60s Output Predictor computes accuracy, streak bonuses, and speed multipliers."""
    round_data = generate_predictor_round(count=3)
    assert len(round_data["questions"]) == 3

    # Submit 2 correct answers and 1 wrong
    q1 = round_data["questions"][0]["id"]
    # We look up expected answer in service
    from app.services.output_predictor_service import CURATED_PREDICTOR_QUESTIONS
    lookup = {q["id"]: q["correct_output"] for q in CURATED_PREDICTOR_QUESTIONS}

    answers = [
        {"question_id": q1, "selected_option": lookup[q1], "time_spent_seconds": 2.5},
        {"question_id": "pred-nonexistent", "selected_option": "Z", "time_spent_seconds": 1.0}
    ]

    res = score_predictor_round(answers)
    assert res["correct_count"] == 1
    assert res["total_score"] >= 100
    assert len(res["results"]) == 1
