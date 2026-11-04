import os
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends, status, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.llm.client import llm_client
from app.services.curriculum_service import seed_curriculum_if_needed
from app.services.link_validator import seed_links_if_needed, validate_all_links
from app.services.scheduler_service import init_scheduler, shutdown_scheduler
from app.api.websocket import websocket_chat_endpoint, router as chat_router
from app.api.routes_quiz import router as quiz_router
from app.api.routes_progress import router as progress_router
from app.api.routes_notifications import router as notifications_router
from app.api.routes_settings import router as settings_router
from app.api.routes_practice import router as practice_router
from app.migrations.runner import run_migrations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("codecoach.main")

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# HTTP Basic Auth (Optional for public deployment)
security = HTTPBasic(auto_error=False)

def check_optional_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if settings.AUTH_USERNAME and settings.AUTH_PASSWORD:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic"}
            )
        correct_username = secrets.compare_digest(credentials.username, settings.AUTH_USERNAME)
        correct_password = secrets.compare_digest(credentials.password, settings.AUTH_PASSWORD)
        if not (correct_username and correct_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect credentials",
                headers={"WWW-Authenticate": "Basic"}
            )
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Run migrations and create database schema
    logger.info("Running database schema migrations...")
    try:
        run_migrations()
    except Exception as me:
        logger.warning("Migration runner note: %s. Ensuring metadata tables...", me)
    Base.metadata.create_all(bind=engine)

    # 2. Seed curriculum and curated links
    db = SessionLocal()
    try:
        seed_curriculum_if_needed(db)
        seed_links_if_needed(db)
    finally:
        db.close()

    # 3. OpenRouter Key & Model Startup Check
    logger.info("Performing OpenRouter credentials and model startup check...")
    check_res = await llm_client.startup_check()
    logger.info("Startup Check Result: %s", check_res.get("status"))

    # 4. Initialize Persistent APScheduler (with misfire grace time for offline catch-up)
    if not os.environ.get("VERCEL"):
        logger.info("Starting persistent scheduler...")
        try:
            init_scheduler()
        except Exception as e:
            logger.warning("Could not initialize background scheduler: %s", e)
    else:
        logger.info("Running on Vercel serverless environment; in-process APScheduler background daemon skipped.")

    # 5. Background initial link health check
    db_links = SessionLocal()
    try:
        # Non-blocking validation
        import asyncio
        asyncio.create_task(validate_all_links(db_links))
    except Exception as e:
        logger.warning("Could not launch startup link validation: %s", e)

    yield

    # Clean shutdown
    logger.info("Shutting down scheduler...")
    shutdown_scheduler()

app = FastAPI(
    title=f"{settings.ASSISTANT_NAME} - C# & .NET Educator",
    description="Real-time educator chatbot that trains in C# and .NET step by step with verified learning.",
    version="1.0.0",
    lifespan=lifespan
)

# Attach limiter to FastAPI state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(chat_router, dependencies=[Depends(check_optional_auth)])
app.include_router(quiz_router, dependencies=[Depends(check_optional_auth)])
app.include_router(progress_router, dependencies=[Depends(check_optional_auth)])
app.include_router(notifications_router, dependencies=[Depends(check_optional_auth)])
app.include_router(settings_router, dependencies=[Depends(check_optional_auth)])
app.include_router(practice_router, dependencies=[Depends(check_optional_auth)])

# WebSocket Chat endpoint with rate limit consideration
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket_chat_endpoint(websocket)

# Mount static directory
static_dir = Path(__file__).resolve().parent.parent / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Service Worker route must be served from root scope for PWA push notifications
@app.get("/sw.js")
async def get_service_worker():
    sw_file = static_dir / "js" / "sw.js"
    return FileResponse(sw_file, media_type="application/javascript")

@app.get("/manifest.json")
async def get_manifest():
    manifest_file = static_dir / "manifest.json"
    return FileResponse(manifest_file, media_type="application/manifest+json")

# Serve Index PWA
@app.get("/")
async def root_index(auth: bool = Depends(check_optional_auth)):
    index_file = static_dir / "index.html"
    return FileResponse(index_file)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "assistant": settings.ASSISTANT_NAME,
        "environment": settings.ENVIRONMENT
    }
