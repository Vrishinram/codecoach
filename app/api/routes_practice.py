"""
FastAPI Router for Practice Arena (Phase 1)
Endpoints for:
1. C# In-browser Code Playground & Sandboxed Execution
2. Bug Hunt Mode
3. Compiler Error & Stack Trace Decoder
4. Refactor Challenge
5. 60-Second Output Predictor Speed Rounds
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    CodeExecutionRequest, CodeExecutionResponse,
    CodingChallengeDTO, ChallengeSubmitRequest, ChallengeSubmitResponse,
    BugHuntScenarioDTO, BugHuntSubmitRequest, BugHuntSubmitResponse,
    CompilerDecodeRequest, CompilerDecodeResponse,
    RefactorScenarioDTO, RefactorSubmitRequest, RefactorGradeResponse,
    OutputPredictorRoundResponse, OutputPredictorSubmitRequest, OutputPredictorSubmitResponse
)
from app.services.code_execution_service import execute_csharp_code, run_challenge_tests
from app.services.bug_hunt_service import list_bug_scenarios, get_bug_scenario, evaluate_bug_hunt_submission
from app.services.compiler_decoder_service import decode_compiler_error
from app.services.refactor_service import list_refactor_scenarios, get_refactor_scenario, grade_refactor_submission
from app.services.output_predictor_service import generate_predictor_round, score_predictor_round

router = APIRouter(prefix="/api/practice", tags=["Practice Arena"])
logger = logging.getLogger("codecoach.api.practice")

# Pre-seeded curated coding challenges
BUILTIN_CHALLENGES = {
    "two-sum-csharp": {
        "id": "two-sum-csharp",
        "title": "Two Sum Target Lookup",
        "difficulty": "Beginner",
        "topic_id": "arrays-and-spans",
        "description": "Given an array of integers and a target sum, output the two 0-based indices whose values sum to the target, formatted as 'index1, index2'.",
        "starter_code": """using System;
using System.Collections.Generic;

public class Solution
{
    public static void Main()
    {
        // Sample test: array = [2, 7, 11, 15], target = 9 -> Output: 0, 1
        int[] nums = { 2, 7, 11, 15 };
        int target = 9;
        
        var map = new Dictionary<int, int>();
        for (int i = 0; i < nums.Length; i++)
        {
            int complement = target - nums[i];
            if (map.ContainsKey(complement))
            {
                Console.WriteLine($"{map[complement]}, {i}");
                return;
            }
            map[nums[i]] = i;
        }
    }
}""",
        "test_cases": [
            {
                "input": "",
                "expected_output": "0, 1",
                "is_hidden": False
            }
        ]
    },
    "palindrome-span": {
        "id": "palindrome-span",
        "title": "Zero-Allocation Palindrome Verification",
        "difficulty": "Intermediate",
        "topic_id": "arrays-and-spans",
        "description": "Verify whether a string is a palindrome using ReadOnlySpan<char> without allocating substring copies on the heap. Output 'True' or 'False'.",
        "starter_code": """using System;

public class Solution
{
    public static void Main()
    {
        string input = "racecar";
        Console.WriteLine(IsPalindrome(input.AsSpan()));
    }

    public static bool IsPalindrome(ReadOnlySpan<char> span)
    {
        int left = 0;
        int right = span.Length - 1;
        while (left < right)
        {
            if (char.ToLower(span[left]) != char.ToLower(span[right]))
                return false;
            left++;
            right--;
        }
        return true;
    }
}""",
        "test_cases": [
            {
                "input": "",
                "expected_output": "True",
                "is_hidden": False
            }
        ]
    }
}

# ----------------------------------------------------------------------------
# 1. In-Browser Code Playground
# ----------------------------------------------------------------------------
@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code_endpoint(req: CodeExecutionRequest):
    """
    Executes C# code inside sandboxed execution container (or LLM fallback simulation).
    """
    res = await execute_csharp_code(
        code=req.code,
        stdin=req.stdin or "",
        timeout_seconds=min(req.timeout_seconds or 5, 8)
    )
    return CodeExecutionResponse(**res)

@router.get("/challenges", response_model=List[CodingChallengeDTO])
async def list_challenges_endpoint():
    """
    Returns available coding challenges with public test cases.
    """
    return [
        CodingChallengeDTO(
            id=c["id"],
            title=c["title"],
            difficulty=c["difficulty"],
            topic_id=c["topic_id"],
            description=c["description"],
            starter_code=c["starter_code"],
            public_test_cases=[tc for tc in c["test_cases"] if not tc.get("is_hidden")]
        )
        for c in BUILTIN_CHALLENGES.values()
    ]

@router.get("/challenges/{challenge_id}", response_model=CodingChallengeDTO)
async def get_challenge_endpoint(challenge_id: str):
    """
    Retrieves details for a specific coding challenge.
    """
    c = BUILTIN_CHALLENGES.get(challenge_id)
    if not c:
        raise HTTPException(status_code=404, detail="Coding challenge not found.")

    return CodingChallengeDTO(
        id=c["id"],
        title=c["title"],
        difficulty=c["difficulty"],
        topic_id=c["topic_id"],
        description=c["description"],
        starter_code=c["starter_code"],
        public_test_cases=[tc for tc in c["test_cases"] if not tc.get("is_hidden")]
    )

@router.post("/challenges/{challenge_id}/submit", response_model=ChallengeSubmitResponse)
async def submit_challenge_endpoint(challenge_id: str, req: ChallengeSubmitRequest):
    """
    Submits student code and runs it against challenge test cases.
    """
    challenge = BUILTIN_CHALLENGES.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Coding challenge not found.")

    res = await run_challenge_tests(challenge, req.code)
    return ChallengeSubmitResponse(**res)

# ----------------------------------------------------------------------------
# 2. Bug Hunt Mode
# ----------------------------------------------------------------------------
@router.get("/bug-hunt", response_model=List[BugHuntScenarioDTO])
async def list_bug_hunt_scenarios():
    """
    Lists all available C# Bug Hunt scenarios.
    """
    return list_bug_scenarios()

@router.get("/bug-hunt/{scenario_id}", response_model=BugHuntScenarioDTO)
async def get_bug_hunt_scenario(scenario_id: str):
    """
    Retrieves a specific Bug Hunt scenario.
    """
    s = get_bug_scenario(scenario_id)
    return BugHuntScenarioDTO(
        id=s["id"],
        title=s["title"],
        difficulty=s["difficulty"],
        topic_id=s["topic_id"],
        description=s["description"],
        code_snippet=s["code_snippet"],
        total_bugs=len(s["buggy_lines"])
    )

@router.post("/bug-hunt/{scenario_id}/submit", response_model=BugHuntSubmitResponse)
async def submit_bug_hunt(scenario_id: str, req: BugHuntSubmitRequest):
    """
    Evaluates clicked line numbers against actual bugs.
    """
    res = evaluate_bug_hunt_submission(scenario_id, req.selected_lines)
    return BugHuntSubmitResponse(**res)

# ----------------------------------------------------------------------------
# 3. Compiler Error Decoder
# ----------------------------------------------------------------------------
@router.post("/compiler-decoder", response_model=CompilerDecodeResponse)
async def decode_compiler_error_endpoint(req: CompilerDecodeRequest):
    """
    Decodes a C# compiler error or runtime stack trace into plain language with causes and code fixes.
    """
    res = await decode_compiler_error(req.error_text)
    return CompilerDecodeResponse(**res)

# ----------------------------------------------------------------------------
# 4. Refactor Challenge
# ----------------------------------------------------------------------------
@router.get("/refactor", response_model=List[RefactorScenarioDTO])
async def list_refactor_scenarios_endpoint():
    """
    Lists available code refactor challenges.
    """
    return list_refactor_scenarios()

@router.get("/refactor/{scenario_id}", response_model=RefactorScenarioDTO)
async def get_refactor_scenario_endpoint(scenario_id: str):
    """
    Retrieves a specific refactor challenge.
    """
    s = get_refactor_scenario(scenario_id)
    return RefactorScenarioDTO(
        id=s["id"],
        title=s["title"],
        topic_id=s["topic_id"],
        description=s["description"],
        bad_code=s["bad_code"]
    )

@router.post("/refactor/{scenario_id}/submit", response_model=RefactorGradeResponse)
async def submit_refactor_endpoint(scenario_id: str, req: RefactorSubmitRequest):
    """
    Grades student refactored code against 4-part rubric.
    """
    res = await grade_refactor_submission(scenario_id, req.refactored_code)
    return RefactorGradeResponse(**res)

# ----------------------------------------------------------------------------
# 5. Output Predictor Speed Rounds
# ----------------------------------------------------------------------------
@router.get("/output-predictor/round", response_model=OutputPredictorRoundResponse)
async def get_output_predictor_round():
    """
    Generates a 60-second speed round of C# output prediction questions.
    """
    res = generate_predictor_round(count=5)
    return OutputPredictorRoundResponse(**res)

@router.post("/output-predictor/submit", response_model=OutputPredictorSubmitResponse)
async def submit_output_predictor_round(req: OutputPredictorSubmitRequest):
    """
    Evaluates speed-round answers, computing total score, streak bonus, and speed multiplier.
    """
    answers_dicts = [a.model_dump() for a in req.answers]
    res = score_predictor_round(answers_dicts)
    return OutputPredictorSubmitResponse(**res)

