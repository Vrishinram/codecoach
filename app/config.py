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

    # Groq Cloud Configuration
    GROQ_API_KEY: str = Field(default="", description="Groq Cloud API Key (gsk_...)")
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "qwen/qwen3.8-27b"

    # xAI Grok Configuration
    XAI_API_KEY: str = Field(default="", description="xAI Grok API Key")
    GROK_API_KEY: str = Field(default="", description="xAI Grok API Key alias")
    GROK_BASE_URL: str = "https://api.x.ai/v1"
    GROK_MODEL: str = "grok-2-latest"

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
    USER_EMAIL: str = "vrishinram4646@gmail.com"

    # Google OAuth 2.0 & Gmail API Configuration
    GOOGLE_OAUTH_CLIENT_ID: str = Field(default="", description="Google OAuth 2.0 Client ID")
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field(default="", description="Google OAuth 2.0 Client Secret")
    GOOGLE_OAUTH_REDIRECT_URI: str = Field(default="", description="Optional explicit Google OAuth redirect URI")

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
    def effective_app_url(self) -> str:
        # Check if user set an explicit external APP_URL
        if self.APP_URL and self.APP_URL != "http://localhost:8000" and not self.APP_URL.startswith("http://localhost"):
            return self.APP_URL
        # On Vercel, use VERCEL_PROJECT_PRODUCTION_URL or VERCEL_URL or default to production app domain
        prod_url = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        if prod_url:
            return f"https://{prod_url}"
        v_url = os.environ.get("VERCEL_URL")
        if v_url:
            return f"https://{v_url}"
        if os.environ.get("VERCEL"):
            return "https://codecoach-blush.vercel.app"
        return self.APP_URL

    @property
    def effective_google_redirect_uri(self) -> str:
        if self.GOOGLE_OAUTH_REDIRECT_URI:
            return self.GOOGLE_OAUTH_REDIRECT_URI.strip()
        return f"{self.effective_app_url.rstrip('/')}/api/auth/google/callback"

    @property
    def storage_engine_label(self) -> str:
        url = self.effective_database_url
        if "postgresql" in url:
            return "PostgreSQL (Hosted)"
        elif "libsql" in url:
            return "Turso LibSQL"
        elif os.environ.get("DATA_BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_READ_WRITE_TOKEN"):
            return "SQLite + Vercel Blob (Durable Serverless)"
        elif "/tmp/" in url:
            return "SQLite (Serverless /tmp Ephemeral)"
        return "SQLite (Local Persistent)"

    @property
    def effective_database_url(self) -> str:
        url = self.DATABASE_URL
        if not url or url == "sqlite:///./codecoach.db":
            # Check standard hosted database environment variables injected by Vercel/Neon/Supabase/Turso
            url = (
                os.environ.get("POSTGRES_URL") or
                os.environ.get("POSTGRES_URL_NON_POOLING") or
                os.environ.get("DATABASE_URL") or
                os.environ.get("SUPABASE_DB_URL") or
                os.environ.get("TURSO_DATABASE_URL") or
                "sqlite:///./codecoach.db"
            ).strip()

        # Normalize postgres:// to postgresql:// for SQLAlchemy compatibility
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        # Vercel and AWS Lambda serverless functions have a read-only filesystem except /tmp for local sqlite fallback
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            if url == "sqlite:///./codecoach.db":
                return "sqlite:////tmp/codecoach.db"
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def active_groq_key(self) -> str:
        """
        Returns a valid Groq API key (starts with gsk_ or explicit GROQ_API_KEY).
        Auto-resolves keys passed in GROK_API_KEY or XAI_API_KEY if prefixed with gsk_.
        """
        for k in [self.GROQ_API_KEY, self.GROK_API_KEY, self.XAI_API_KEY]:
            val = (k or "").strip()
            if val.startswith("gsk_"):
                return val
        return (self.GROQ_API_KEY or "").strip()

    @property
    def active_grok_key(self) -> str:
        """
        Returns a valid xAI Grok API key (non-gsk_ key in XAI_API_KEY or GROK_API_KEY).
        """
        for k in [self.XAI_API_KEY, self.GROK_API_KEY]:
            val = (k or "").strip()
            if val and not val.startswith("gsk_"):
                return val
        return ""

    @property
    def effective_model_name(self) -> str:
        if self.active_groq_key:
            return self.GROQ_MODEL or "qwen/qwen3.8-27b"
        if self.active_grok_key:
            return self.GROK_MODEL or "grok-2-latest"
        if self.GOOGLE_API_KEY:
            return self.GEMINI_MODEL or "gemini-3.5-flash"
        return self.MODEL_NAME

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

