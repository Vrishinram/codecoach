import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Assistant Identity
    ASSISTANT_NAME: str = "CodeCoach"
    APP_URL: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"
    AUTH_USERNAME: str = ""
    AUTH_PASSWORD: str = ""

    # OpenRouter LLM Configuration
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL_NAME: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    FALLBACK_MODELS: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,xingchen-agi/xing4.0-29b-a4b:free,openai/gpt-4o-mini"
    TEMPERATURE: float = 0.3
    MAX_TOKENS: int = 2048

    # Google Gemini Configuration
    GOOGLE_API_KEY: str = Field(default="", description="Google Gemini API Key")
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Training & Verification Parameters
    SET_SIZE: int = 25
    PASS_SCORE: int = 70
    MASTERY_SCORE: int = 85
    RATE_LIMIT_PER_MINUTE: int = 30

    # SMTP Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "CodeCoach <noreply@codecoach.local>"
    USER_EMAIL: str = ""

    # Web Push (VAPID)
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:admin@example.com"
    NTFY_TOPIC: str = ""

    # Scheduling
    REMINDER_TIMES: str = "08:00,20:00"
    TIMEZONE: str = "Asia/Kolkata"

    # SQLite
    DATABASE_URL: str = "sqlite:///./codecoach.db"

    @property
    def effective_database_url(self) -> str:
        # Vercel and AWS Lambda serverless functions have a read-only filesystem except /tmp
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            if self.DATABASE_URL == "sqlite:///./codecoach.db":
                return "sqlite:////tmp/codecoach.db"
        return self.DATABASE_URL

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def fallback_model_list(self) -> List[str]:
        if not self.FALLBACK_MODELS:
            return []
        return [m.strip() for m in self.FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def reminder_time_list(self) -> List[str]:
        if not self.REMINDER_TIMES:
            return ["08:00", "20:00"]
        return [t.strip() for t in self.REMINDER_TIMES.split(",") if t.strip()]

settings = Settings()

