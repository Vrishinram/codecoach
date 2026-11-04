import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from openai import RateLimitError
from app.llm.client import LLMClient
from app.llm.grader import grade_teach_back

def test_friendly_error_messages():
    client = LLMClient()
    assert "Authentication Error (401)" in client._friendly_error_message(Exception("401 unauthorized"), "model-a")
    assert "Payment Required (402)" in client._friendly_error_message(Exception("402 out of credits"), "model-a")
    assert "Rate Limit Exceeded (429)" in client._friendly_error_message(Exception("429 rate limit"), "model-a")

@pytest.mark.asyncio
async def test_llm_fallback_and_retry(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "_get_models_to_try", lambda: ["test-primary", "test-fallback"])

    call_counts = {"primary": 0, "fallback": 0}

    async def mock_create(model, **kwargs):
        if model == "test-primary":
            call_counts["primary"] += 1
            # Simulate 429 RateLimit on primary
            resp = MagicMock()
            resp.status_code = 429
            raise RateLimitError("429 Too Many Requests", response=resp, body=None)
        else:
            call_counts["fallback"] += 1
            # Fallback succeeds
            mock_res = MagicMock()
            mock_res.choices = [MagicMock(message=MagicMock(content="Fallback response"))]
            mock_res.usage = MagicMock(prompt_tokens=10, completion_tokens=10, total_tokens=20)
            return mock_res

    # Mock OpenAI client
    mock_async_client = MagicMock()
    mock_async_client.chat.completions.create = mock_create
    monkeypatch.setattr(client, "get_client", lambda: mock_async_client)

    result = await client.generate_completion(messages=[{"role": "user", "content": "hi"}])
    assert result["content"] == "Fallback response"
    assert call_counts["primary"] >= 1
    assert call_counts["fallback"] >= 1

@pytest.mark.asyncio
async def test_validated_json_with_one_retry(monkeypatch):
    client = LLMClient()

    attempts = [0]

    async def mock_generate_completion(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] == 1:
            # First attempt returns malformed JSON with markdown quotes
            return {"content": "```json\n{ invalid: json missing quotes }\n```", "model": "test-model", "usage": {}}
        else:
            # Second attempt returns valid JSON
            return {"content": '{"score": 88.0, "passed": true}', "model": "test-model", "usage": {}}

    monkeypatch.setattr(client, "generate_completion", mock_generate_completion)

    parsed = await client.generate_validated_json(messages=[{"role": "user", "content": "generate"}])
    assert parsed["data"]["score"] == 88.0
    assert parsed["data"]["passed"] is True
    assert attempts[0] == 2

@pytest.mark.asyncio
async def test_teach_back_grader_schema_validation(db_session, monkeypatch):
    async def mock_json(*args, **kwargs):
        return {
            "data": {
                "accuracy_score": 90.0,
                "completeness_score": 85.0,
                "clarity_score": 95.0,
                "overall_score": 89.0,
                "passed": True,
                "missing_points": ["Could mention Span<T>"],
                "feedback": "Excellent explanation of value vs reference types."
            },
            "model": "test-model",
            "usage": {"total_tokens": 120}
        }

    monkeypatch.setattr("app.llm.grader.llm_client.generate_validated_json", mock_json)

    res = await grade_teach_back(
        topic_title="Variables & Types",
        subtopics=["value types", "reference types"],
        student_explanation="Value types hold their data on the stack directly, while reference types store addresses to the heap.",
        db=db_session
    )

    assert res["overall_score"] == 89.0
    assert res["passed"] is True
    assert len(res["missing_points"]) == 1
    assert "Excellent" in res["feedback"]

