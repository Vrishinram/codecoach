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

@pytest.mark.asyncio
async def test_grok_configuration_and_model_priority(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key-12345")
    from app.config import Settings
    cfg = Settings()
    assert cfg.effective_model_name == "grok-2-latest"
    assert cfg.GROK_BASE_URL == "https://api.x.ai/v1"

    client = LLMClient()
    models = client._get_models_to_try()
    assert models[0] == "grok-2-latest"
    assert "grok-2-mini" in models

    grok_cli = client.get_grok_client()
    assert grok_cli is not None
    assert str(grok_cli.base_url).rstrip("/") == "https://api.x.ai/v1"

@pytest.mark.asyncio
async def test_grok_startup_check_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key-12345")
    client = LLMClient()

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="grok-pong"))]
    mock_create = AsyncMock(return_value=mock_resp)

    mock_grok = MagicMock()
    mock_grok.chat.completions.create = mock_create
    monkeypatch.setattr(client, "get_grok_client", lambda: mock_grok)

    check = await client.startup_check()
    assert check["status"] == "ok"
    assert check["provider"] == "xai_grok"
    assert check["model"] == "grok-2-latest"
    assert check["response"] == "grok-pong"

@pytest.mark.asyncio
async def test_grok_completion_and_streaming(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key-12345")
    client = LLMClient()

    # 1. Non-streaming completion
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Hello from Grok!"))]
    mock_resp.usage = MagicMock(prompt_tokens=12, completion_tokens=8, total_tokens=20)
    mock_create = AsyncMock(return_value=mock_resp)

    mock_grok = MagicMock()
    mock_grok.chat.completions.create = mock_create
    monkeypatch.setattr(client, "get_grok_client", lambda: mock_grok)

    res = await client.generate_completion(messages=[{"role": "user", "content": "hello"}])
    assert res["content"] == "Hello from Grok!"
    assert res["model"] == "grok-2-latest"
    assert res["usage"]["total_tokens"] == 20

    # 2. Streaming completion
    async def mock_stream_iter():
        chunks = ["Hello", " ", "Gotham", "!"]
        for c in chunks:
            delta = MagicMock()
            delta.content = c
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            yield chunk

    mock_stream_create = AsyncMock(return_value=mock_stream_iter())
    mock_grok.chat.completions.create = mock_stream_create

    tokens = []
    done_msg = None
    async for item in client.stream_chat(messages=[{"role": "user", "content": "stream test"}]):
        if item.get("type") == "token":
            tokens.append(item.get("content"))
        elif item.get("type") == "done":
            done_msg = item

    assert "".join(tokens) == "Hello Gotham!"
    assert done_msg is not None
    assert done_msg["model"] == "grok-2-latest"

@pytest.mark.asyncio
async def test_groq_configuration_and_model_priority(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_groq_key_12345")
    from app.config import Settings
    cfg = Settings()
    assert cfg.active_groq_key == "gsk_test_groq_key_12345"
    assert cfg.effective_model_name == "qwen/qwen3.8-27b"
    assert cfg.GROQ_BASE_URL == "https://api.groq.com/openai/v1"

    client = LLMClient()
    models = client._get_models_to_try()
    assert models[0] == "qwen/qwen3.8-27b"
    assert "openai/gpt-oss-120b" in models

    groq_cli = client.get_groq_client()
    assert groq_cli is not None
    assert str(groq_cli.base_url).rstrip("/") == "https://api.groq.com/openai/v1"

@pytest.mark.asyncio
async def test_groq_startup_check_and_completion(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_groq_key_12345")
    client = LLMClient()

    # 1. Startup check
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="groq-pong"))]
    mock_create = AsyncMock(return_value=mock_resp)

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = mock_create
    monkeypatch.setattr(client, "get_groq_client", lambda: mock_groq)

    check = await client.startup_check()
    assert check["status"] == "ok"
    assert check["provider"] == "groq"
    assert check["model"] == "qwen/qwen3.8-27b"

    # 2. Completion
    mock_resp_comp = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "Fast C# output from Groq"
    mock_msg.reasoning = None
    mock_resp_comp.choices = [MagicMock(message=mock_msg)]
    mock_resp_comp.usage = MagicMock(prompt_tokens=10, completion_tokens=8, total_tokens=18)
    mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp_comp)

    res = await client.generate_completion(messages=[{"role": "user", "content": "hello"}])
    assert res["content"] == "Fast C# output from Groq"
    assert res["model"] == "qwen/qwen3.8-27b"
    assert res["usage"]["total_tokens"] == 18



