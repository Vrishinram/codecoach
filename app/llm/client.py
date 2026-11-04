import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
import httpx
from openai import AsyncOpenAI, APIError, AuthenticationError, RateLimitError, APITimeoutError

from app.config import settings

logger = logging.getLogger("codecoach.llm")

class LLMClient:
    """
    Multi-Provider LLM Client supporting OpenRouter and Google Gemini APIs.
    Features:
    - Base URL set to OpenRouter with automatic Google Gemini provider support
    - API keys safely loaded from settings/env only, never leaked
    - Streaming support over AsyncGenerator
    - Automatic retry with exponential backoff on 429/5xx
    - Graceful fallback across fallback_models list
    - Friendly error categorization
    - Robust JSON extraction with 1 retry without relying on provider JSON mode
    """

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._grok_client: Optional[AsyncOpenAI] = None
        self._groq_client: Optional[AsyncOpenAI] = None

    def get_client(self) -> AsyncOpenAI:
        from app.config import Settings
        current_key = Settings().OPENROUTER_API_KEY
        if self._client is None or getattr(self, "_current_key", None) != current_key:
            self._current_key = current_key
            self._client = AsyncOpenAI(
                api_key=current_key,
                base_url=settings.OPENROUTER_BASE_URL,
                http_client=httpx.AsyncClient(timeout=60.0)
            )
        return self._client

    def get_groq_client(self) -> Optional[AsyncOpenAI]:
        from app.config import Settings
        cfg = Settings()
        key = cfg.active_groq_key
        if not key:
            return None
        if self._groq_client is None or getattr(self, "_current_groq_key", None) != key:
            self._current_groq_key = key
            self._groq_client = AsyncOpenAI(
                api_key=key,
                base_url=cfg.GROQ_BASE_URL,
                http_client=httpx.AsyncClient(timeout=60.0)
            )
        return self._groq_client

    def get_grok_client(self) -> Optional[AsyncOpenAI]:
        from app.config import Settings
        cfg = Settings()
        key = cfg.active_grok_key
        if not key:
            return None
        if self._grok_client is None or getattr(self, "_current_grok_key", None) != key:
            self._current_grok_key = key
            self._grok_client = AsyncOpenAI(
                api_key=key,
                base_url=cfg.GROK_BASE_URL,
                http_client=httpx.AsyncClient(timeout=60.0)
            )
        return self._grok_client

    async def startup_check(self) -> Dict[str, Any]:
        """
        Validates the configured keys and primary model at server startup.
        Priority: Groq Cloud -> xAI Grok -> Google Gemini -> OpenRouter.
        """
        from app.config import Settings
        cfg = Settings()

        # 1. Check Groq Cloud if key configured
        groq_client = self.get_groq_client()
        if groq_client:
            model = cfg.GROQ_MODEL or "qwen/qwen3.8-27b"
            try:
                response = await groq_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    temperature=0.0
                )
                logger.info("Startup Check: Successfully verified Groq Cloud with model '%s'", model)
                return {
                    "status": "ok",
                    "provider": "groq",
                    "model": model,
                    "response": response.choices[0].message.content
                }
            except Exception as e:
                logger.warning("Startup Check for Groq Cloud failed: %s. Falling back to Grok/Gemini/OpenRouter.", e)

        # 2. Check xAI Grok if key configured
        grok_client = self.get_grok_client()
        if grok_client:
            model = cfg.GROK_MODEL or "grok-2-latest"
            try:
                response = await grok_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    temperature=0.0
                )
                logger.info("Startup Check: Successfully verified xAI Grok with model '%s'", model)
                return {
                    "status": "ok",
                    "provider": "xai_grok",
                    "model": model,
                    "response": response.choices[0].message.content
                }
            except Exception as e:
                logger.warning("Startup Check for xAI Grok failed: %s. Falling back to Gemini/OpenRouter.", e)

        # 2. Check Google Gemini if configured
        if cfg.GOOGLE_API_KEY:
            try:
                model = cfg.GEMINI_MODEL or "gemini-3.5-flash"
                res = await self._generate_gemini(
                    messages=[{"role": "user", "content": "ping"}],
                    model=model,
                    max_tokens=5
                )
                logger.info("Startup Check: Successfully verified Google Gemini with model '%s'", model)
                return {
                    "status": "ok",
                    "provider": "google",
                    "model": model,
                    "response": res.get("content")
                }
            except Exception as e:
                logger.warning("Startup Check for Google Gemini failed: %s. Falling back to OpenRouter check.", e)

        # 3. Check OpenRouter
        if not cfg.OPENROUTER_API_KEY or cfg.OPENROUTER_API_KEY.startswith("dummy"):
            logger.warning("Startup Check: OPENROUTER_API_KEY is not set or using dummy key.")
            return {
                "status": "warning",
                "message": "No valid LLM key (xAI Grok, Gemini, or OpenRouter) configured. Please update your environment."
            }

        client = self.get_client()
        try:
            model = cfg.MODEL_NAME
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0.0
            )
            logger.info("Startup Check: Successfully verified OpenRouter connection and model '%s'", model)
            return {
                "status": "ok",
                "provider": "openrouter",
                "model": model,
                "response": response.choices[0].message.content
            }
        except AuthenticationError as e:
            logger.error("Startup Check: Authentication failed (401). Please check OPENROUTER_API_KEY.")
            return {"status": "error", "code": 401, "message": "Invalid OpenRouter API Key. Please verify .env."}
        except RateLimitError as e:
            logger.warning("Startup Check: Rate limited or insufficient credits (429/402).")
            return {"status": "error", "code": 429, "message": "Rate limited or out of credits on OpenRouter."}
        except Exception as e:
            logger.error("Startup Check error: %s", str(e))
            return {"status": "error", "message": str(e)}

    def _get_models_to_try(self) -> List[str]:
        from app.config import Settings
        current_settings = Settings()
        models = []
        if current_settings.active_groq_key:
            models.append(current_settings.GROQ_MODEL or "qwen/qwen3.8-27b")
            for gm in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
                if gm not in models:
                    models.append(gm)
        if current_settings.active_grok_key:
            models.append(current_settings.GROK_MODEL or "grok-2-latest")
            models.append("grok-2-mini")
        if current_settings.GOOGLE_API_KEY:
            models.append(current_settings.GEMINI_MODEL or "gemini-3.5-flash")
        if current_settings.MODEL_NAME and current_settings.MODEL_NAME not in models:
            models.append(current_settings.MODEL_NAME)
        for fb in current_settings.fallback_model_list:
            if fb not in models:
                models.append(fb)
        return models

    def _friendly_error_message(self, error: Exception, model: str) -> str:
        error_str = str(error)
        if "401" in error_str or isinstance(error, AuthenticationError):
            return "Authentication Error (401): The API key is missing or invalid. Please check your .env file."
        elif "402" in error_str or "credits" in error_str.lower():
            return "Payment Required (402): Your API balance has run out. Please add credits or use a free model."
        elif "429" in error_str or isinstance(error, RateLimitError):
            return f"Rate Limit Exceeded (429): Too many requests to model '{model}'. Exponential backoff exhausted."
        elif isinstance(error, APITimeoutError):
            return f"Timeout Error: Model '{model}' took too long to respond. Please try again."
        elif "404" in error_str or "model" in error_str.lower() and "not found" in error_str.lower():
            return f"Model Unavailable: Model '{model}' could not be reached."
        return f"LLM Service Error: {error_str}"

    async def _stream_gemini(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        model: str = "gemini-3.5-flash",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        from app.config import Settings
        key = Settings().GOOGLE_API_KEY
        if not key:
            raise ValueError("GOOGLE_API_KEY not set")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={key}"

        contents = []
        for m in messages:
            role = "model" if m.get("role") in ("assistant", "model") else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        payload = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        generation_config = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if generation_config:
            payload["generationConfig"] = generation_config

        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        completion_tokens_est = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code >= 400:
                    err_body = await response.aread()
                    raise RuntimeError(f"Gemini HTTP {response.status_code}: {err_body.decode('utf-8')}")

                buffer = ""
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            chunk_json = json.loads(data_str)
                            cands = chunk_json.get("candidates", [])
                            if cands and "content" in cands[0] and "parts" in cands[0]["content"]:
                                text = cands[0]["content"]["parts"][0].get("text", "")
                                if text:
                                    completion_tokens_est += max(1, len(text) // 4)
                                    yield {"type": "token", "content": text, "model": model}
                        except Exception:
                            continue

        prompt_tokens_est = max(1, prompt_chars // 4)
        yield {
            "type": "done",
            "model": model,
            "usage": {
                "prompt_tokens": prompt_tokens_est,
                "completion_tokens": completion_tokens_est,
                "total_tokens": prompt_tokens_est + completion_tokens_est
            }
        }

    async def _generate_gemini(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        model: str = "gemini-3.5-flash",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        from app.config import Settings
        key = Settings().GOOGLE_API_KEY
        if not key:
            raise ValueError("GOOGLE_API_KEY not set")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

        contents = []
        for m in messages:
            role = "model" if m.get("role") in ("assistant", "model") else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        payload = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        generation_config = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if response_mime_type:
            generation_config["responseMimeType"] = response_mime_type
        if generation_config:
            payload["generationConfig"] = generation_config

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            content = parts[0].get("text", "")

            prompt_chars = sum(len(m.get("content", "")) for m in messages)
            p_tokens = max(1, prompt_chars // 4)
            c_tokens = max(1, len(content) // 4)

            return {
                "content": content,
                "model": model,
                "usage": {
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "total_tokens": p_tokens + c_tokens
                }
            }

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams answer tokens over an async generator with retry and fallback across models and providers.
        """
        from app.config import Settings
        cfg = Settings()
        models = self._get_models_to_try()
        last_error = None

        # Check providers in order: Groq Cloud -> xAI Grok -> Gemini -> OpenRouter
        for model in models:
            is_groq_native = bool(cfg.active_groq_key and (model.startswith("qwen") or model.startswith("openai/gpt-oss") or model == cfg.GROQ_MODEL or "groq" in model.lower()))
            if is_groq_native:
                groq_client = self.get_groq_client()
                if groq_client:
                    temp = temperature if temperature is not None else settings.TEMPERATURE
                    m_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS
                    full_messages = []
                    if system_prompt:
                        full_messages.append({"role": "system", "content": system_prompt})
                    full_messages.extend(messages)
                    for attempt in range(2):
                        try:
                            logger.debug("Streaming with Groq Cloud (%s)", model)
                            stream = await groq_client.chat.completions.create(
                                model=model,
                                messages=full_messages,
                                temperature=temp,
                                max_tokens=m_tokens,
                                stream=True
                            )
                            prompt_chars = sum(len(m.get("content", "")) for m in full_messages)
                            completion_tokens_est = 0
                            async for chunk in stream:
                                delta = chunk.choices[0].delta if chunk.choices else None
                                token_text = (getattr(delta, "content", None) or "")
                                if not token_text and getattr(delta, "reasoning", None):
                                    token_text = getattr(delta, "reasoning") or ""
                                if token_text:
                                    completion_tokens_est += max(1, len(token_text) // 4)
                                    yield {"type": "token", "content": token_text, "model": model}
                            prompt_tokens_est = max(1, prompt_chars // 4)
                            yield {
                                "type": "done",
                                "model": model,
                                "usage": {
                                    "prompt_tokens": prompt_tokens_est,
                                    "completion_tokens": completion_tokens_est,
                                    "total_tokens": prompt_tokens_est + completion_tokens_est
                                }
                            }
                            return
                        except Exception as e:
                            logger.warning("Groq Cloud stream %s failed: %s. Trying fallback...", model, e)
                            last_error = e
                            break

            is_grok_native = bool(cfg.active_grok_key and (model.startswith("grok") or "grok" in model.lower()))
            if is_grok_native:
                grok_client = self.get_grok_client()
                if grok_client:
                    temp = temperature if temperature is not None else settings.TEMPERATURE
                    m_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS
                    full_messages = []
                    if system_prompt:
                        full_messages.append({"role": "system", "content": system_prompt})
                    full_messages.extend(messages)
                    for attempt in range(2):
                        try:
                            logger.debug("Streaming with xAI Grok (%s)", model)
                            stream = await grok_client.chat.completions.create(
                                model=model,
                                messages=full_messages,
                                temperature=temp,
                                max_tokens=m_tokens,
                                stream=True
                            )
                            prompt_chars = sum(len(m.get("content", "")) for m in full_messages)
                            completion_tokens_est = 0
                            async for chunk in stream:
                                delta = chunk.choices[0].delta if chunk.choices else None
                                token_text = (delta.content if (delta and delta.content) else "") or ""
                                if token_text:
                                    completion_tokens_est += max(1, len(token_text) // 4)
                                    yield {"type": "token", "content": token_text, "model": model}
                            prompt_tokens_est = max(1, prompt_chars // 4)
                            yield {
                                "type": "done",
                                "model": model,
                                "usage": {
                                    "prompt_tokens": prompt_tokens_est,
                                    "completion_tokens": completion_tokens_est,
                                    "total_tokens": prompt_tokens_est + completion_tokens_est
                                }
                            }
                            return
                        except Exception as e:
                            logger.warning("xAI Grok stream %s failed: %s. Trying fallback...", model, e)
                            last_error = e
                            break

            is_gemini_native = (cfg.GOOGLE_API_KEY and ("gemini" in model.lower() or model.startswith("models/")))
            if is_gemini_native:
                clean_model = model.replace("models/", "")
                try:
                    logger.debug("Streaming with native Google Gemini (%s)", clean_model)
                    async for chunk in self._stream_gemini(
                        messages=messages,
                        system_prompt=system_prompt,
                        model=clean_model,
                        temperature=temperature,
                        max_tokens=max_tokens
                    ):
                        yield chunk
                    return
                except Exception as e:
                    logger.warning("Gemini model %s failed: %s. Trying fallback...", model, e)
                    last_error = e
                    continue

            # OpenRouter Streaming
            client = self.get_client()
            temp = temperature if temperature is not None else settings.TEMPERATURE
            m_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS

            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            for attempt in range(2):
                try:
                    logger.debug("Streaming with OpenRouter model %s (attempt %d)", model, attempt + 1)
                    stream = await client.chat.completions.create(
                        model=model,
                        messages=full_messages,
                        temperature=temp,
                        max_tokens=m_tokens,
                        stream=True
                    )

                    prompt_chars = sum(len(m.get("content", "")) for m in full_messages)
                    completion_tokens_est = 0

                    async for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        token_text = (delta.content if (delta and delta.content) else (getattr(delta, "reasoning", "") if delta else "")) or ""
                        if token_text:
                            completion_tokens_est += max(1, len(token_text) // 4)
                            yield {"type": "token", "content": token_text, "model": model}

                    prompt_tokens_est = max(1, prompt_chars // 4)
                    yield {
                        "type": "done",
                        "model": model,
                        "usage": {
                            "prompt_tokens": prompt_tokens_est,
                            "completion_tokens": completion_tokens_est,
                            "total_tokens": prompt_tokens_est + completion_tokens_est
                        }
                    }
                    return

                except (RateLimitError, APIError, APITimeoutError) as e:
                    last_error = e
                    status_code = getattr(e, "status_code", None)
                    if status_code in (401, 402):
                        # Try next model if credits or auth fail on this specific model
                        break
                    
                    backoff = 2 ** (attempt + 1)
                    await asyncio.sleep(backoff)
                except Exception as e:
                    last_error = e
                    break

        yield {"type": "error", "error": self._friendly_error_message(last_error or Exception("All models exhausted"), models[-1])}

    async def generate_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Non-streaming completion with automatic fallback and retry across Gemini & OpenRouter.
        """
        from app.config import Settings
        cfg = Settings()
        models = self._get_models_to_try()
        last_error = None

        for model in models:
            is_groq_native = bool(cfg.active_groq_key and (model.startswith("qwen") or model.startswith("openai/gpt-oss") or model == cfg.GROQ_MODEL or "groq" in model.lower()))
            if is_groq_native:
                groq_client = self.get_groq_client()
                if groq_client:
                    temp = temperature if temperature is not None else settings.TEMPERATURE
                    m_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS
                    full_messages = []
                    if system_prompt:
                        full_messages.append({"role": "system", "content": system_prompt})
                    full_messages.extend(messages)
                    for attempt in range(2):
                        try:
                            logger.debug("Generating completion with Groq Cloud (%s)", model)
                            resp = await groq_client.chat.completions.create(
                                model=model,
                                messages=full_messages,
                                temperature=temp,
                                max_tokens=m_tokens,
                                stream=False
                            )
                            msg = resp.choices[0].message
                            content = getattr(msg, "content", None) or getattr(msg, "reasoning", None) or ""
                            prompt_chars = sum(len(m.get("content", "")) for m in full_messages)
                            p_tokens = getattr(resp.usage, "prompt_tokens", max(1, prompt_chars // 4)) if getattr(resp, "usage", None) else max(1, prompt_chars // 4)
                            c_tokens = getattr(resp.usage, "completion_tokens", max(1, len(content) // 4)) if getattr(resp, "usage", None) else max(1, len(content) // 4)
                            return {
                                "content": content,
                                "model": model,
                                "usage": {
                                    "prompt_tokens": p_tokens,
                                    "completion_tokens": c_tokens,
                                    "total_tokens": p_tokens + c_tokens
                                }
                            }
                        except Exception as e:
                            logger.warning("Groq Cloud completion %s failed: %s. Trying fallback...", model, e)
                            last_error = e
                            break

            is_grok_native = bool(cfg.active_grok_key and (model.startswith("grok") or "grok" in model.lower()))
            if is_grok_native:
                grok_client = self.get_grok_client()
                if grok_client:
                    temp = temperature if temperature is not None else settings.TEMPERATURE
                    m_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS
                    full_messages = []
                    if system_prompt:
                        full_messages.append({"role": "system", "content": system_prompt})
                    full_messages.extend(messages)
                    for attempt in range(2):
                        try:
                            logger.debug("Generating completion with xAI Grok (%s)", model)
                            resp = await grok_client.chat.completions.create(
                                model=model,
                                messages=full_messages,
                                temperature=temp,
                                max_tokens=m_tokens,
                                stream=False
                            )
                            content = resp.choices[0].message.content or ""
                            prompt_chars = sum(len(m.get("content", "")) for m in full_messages)
                            p_tokens = getattr(resp.usage, "prompt_tokens", max(1, prompt_chars // 4)) if getattr(resp, "usage", None) else max(1, prompt_chars // 4)
                            c_tokens = getattr(resp.usage, "completion_tokens", max(1, len(content) // 4)) if getattr(resp, "usage", None) else max(1, len(content) // 4)
                            return {
                                "content": content,
                                "model": model,
                                "usage": {
                                    "prompt_tokens": p_tokens,
                                    "completion_tokens": c_tokens,
                                    "total_tokens": p_tokens + c_tokens
                                }
                            }
                        except Exception as e:
                            logger.warning("xAI Grok completion %s failed: %s. Trying fallback...", model, e)
                            last_error = e
                            break

            is_gemini_native = (cfg.GOOGLE_API_KEY and ("gemini" in model.lower() or model.startswith("models/")))
            if is_gemini_native:
                clean_model = model.replace("models/", "")
                try:
                    return await self._generate_gemini(
                        messages=messages,
                        system_prompt=system_prompt,
                        model=clean_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_mime_type=response_mime_type
                    )
                except Exception as e:
                    logger.warning("Gemini model %s failed: %s. Trying fallback...", model, e)
                    last_error = e
                    continue

            # OpenRouter non-streaming
            client = self.get_client()
            temp = temperature if temperature is not None else settings.TEMPERATURE
            m_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS

            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            for attempt in range(2):
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=full_messages,
                        temperature=temp,
                        max_tokens=m_tokens,
                        stream=False
                    )
                    content = response.choices[0].message.content or getattr(response.choices[0].message, "reasoning", "") or ""
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", len(str(full_messages)) // 4),
                        "completion_tokens": getattr(response.usage, "completion_tokens", len(content) // 4),
                        "total_tokens": getattr(response.usage, "total_tokens", (len(str(full_messages)) + len(content)) // 4)
                    }
                    return {"content": content, "model": model, "usage": usage}
                except (RateLimitError, APIError, APITimeoutError) as e:
                    last_error = e
                    status_code = getattr(e, "status_code", None)
                    if status_code in (401, 402):
                        break
                    backoff = 2 ** (attempt + 1)
                    await asyncio.sleep(backoff)
                except Exception as e:
                    last_error = e
                    break

        raise RuntimeError(self._friendly_error_message(last_error or Exception("All models failed"), models[-1]))

    async def generate_validated_json(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = 8192
    ) -> Dict[str, Any]:
        """
        Generates structured JSON with 1 retry on invalid format.
        """
        prompt_with_instructions = messages.copy()
        json_instruction = (
            "\n\nCRITICAL INSTRUCTION: You MUST return ONLY valid, parseable JSON code. "
            "Do NOT include markdown backticks like ```json ... ``` or any introductory or concluding text."
        )
        if prompt_with_instructions:
            prompt_with_instructions[-1]["content"] += json_instruction

        for attempt in range(2):
            result = await self.generate_completion(
                messages=prompt_with_instructions,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=max_tokens,
                response_mime_type="application/json"
            )
            raw_text = result["content"].strip()
            
            cleaned = raw_text
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                parsed = json.loads(cleaned)
                return {
                    "data": parsed,
                    "model": result["model"],
                    "usage": result["usage"]
                }
            except json.JSONDecodeError as json_err:
                logger.warning("JSON decode failed on attempt %d: %s.", attempt + 1, json_err)
                if attempt == 0:
                    prompt_with_instructions.append({"role": "assistant", "content": raw_text})
                    prompt_with_instructions.append({
                        "role": "user",
                        "content": f"Your response was not valid JSON ({str(json_err)}). Please return ONLY raw valid JSON fixing any syntax errors."
                    })
                else:
                    raise ValueError(f"Failed to parse valid JSON from LLM output after retry: {str(json_err)}")

llm_client = LLMClient()
