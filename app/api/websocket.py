import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import CurriculumTopic, TopicProgress, TokenUsage, UserProfile
from app.llm.client import llm_client
from app.llm.prompts import get_educator_system_prompt
from app.services.curriculum_service import update_user_activity_streak

logger = logging.getLogger("codecoach.chat")

router = APIRouter(prefix="/api", tags=["Chat"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

manager = ConnectionManager()

def process_slash_command(command_text: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Evaluates slash commands: /start <topic>, /next, /hint, /skip, /explain, /progress, /links, /videos, /review
    Returns a response dict if handled, or None.
    """
    raw = command_text.strip()
    if not raw.startswith("/"):
        return None

    parts = raw.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/start":
        if not arg:
            topics = db.query(CurriculumTopic).all()
            lines = [f"• `{t.id}`: {t.title}" for t in topics[:8]]
            msg = "**To begin training on a topic, use `/start <topic_id>`:**\n\n" + "\n".join(lines)
            return {"type": "message", "sender": "assistant", "content": msg}

        topic = db.query(CurriculumTopic).filter(
            (CurriculumTopic.id == arg) | (CurriculumTopic.title.ilike(f"%{arg}%"))
        ).first()
        if not topic:
            return {
                "type": "message",
                "sender": "assistant",
                "content": f"Topic '{arg}' was not found. Open the Roadmap sidebar to view all curriculum topics."
            }

        return {
            "type": "command_action",
            "action": "start_topic",
            "topic_id": topic.id,
            "message": f"Starting training set for **{topic.title}**."
        }

    elif cmd == "/next":
        return {
            "type": "command_action",
            "action": "next_question",
            "message": "Moving to next question..."
        }

    elif cmd == "/hint":
        return {
            "type": "command_action",
            "action": "request_hint",
            "message": "Retrieving hint for current question..."
        }

    elif cmd == "/skip":
        return {
            "type": "command_action",
            "action": "skip_question",
            "message": "Skipping to next question..."
        }

    elif cmd == "/progress":
        unlocked = db.query(TopicProgress).filter(TopicProgress.unlocked == True).count()
        mastered = db.query(TopicProgress).filter(TopicProgress.status == "Mastered").count()
        profile = db.query(UserProfile).first()
        streak = profile.current_streak if profile else 1

        msg = (
            f"### 📊 Your C# Learning Status\n\n"
            f"- **Daily Streak**: 🔥 {streak} days\n"
            f"- **Unlocked Topics**: {unlocked}\n"
            f"- **Mastered Topics**: 🏆 {mastered}\n\n"
            f"Click the **Dashboard** tab above for in-depth mastery analytics and score trends!"
        )
        return {"type": "message", "sender": "assistant", "content": msg}

    elif cmd in ("/links", "/videos"):
        return {
            "type": "command_action",
            "action": "show_links",
            "message": "Opening curated official learning resources..."
        }

    elif cmd == "/review":
        return {
            "type": "command_action",
            "action": "open_reviews",
            "message": "Loading questions due for spaced repetition review..."
        }

    return None

@router.post("/chat")
async def http_chat_endpoint(request: Request, db: Session = Depends(get_db)):
    """
    HTTP chat fallback for serverless environments (like Vercel) where WebSockets are not sustained.
    """
    data = await request.json()
    user_msg = data.get("content", "").strip()
    history = data.get("history", [])

    if not user_msg:
        return {"type": "message", "sender": "assistant", "content": "Please enter a message or command."}

    update_user_activity_streak(db)

    cmd_res = process_slash_command(user_msg, db)
    if cmd_res:
        return cmd_res

    messages = []
    for h in history[-8:]:
        messages.append({"role": h.get("sender", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": user_msg})

    res = await llm_client.generate_completion(
        messages=messages,
        system_prompt=get_educator_system_prompt()
    )

    usage = res.get("usage", {})
    try:
        tu = TokenUsage(
            model=res.get("model", settings.MODEL_NAME),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            operation="chat_http"
        )
        db.add(tu)
        db.commit()
    except Exception as e:
        logger.error("Error saving token usage: %s", e)
        db.rollback()

    return {
        "type": "message",
        "sender": "assistant",
        "content": res.get("content", ""),
        "model": res.get("model")
    }

@router.post("/chat/stream")
async def http_chat_stream_endpoint(request: Request, db: Session = Depends(get_db)):
    """
    HTTP Server-Sent Events (SSE) streaming endpoint.
    """
    data = await request.json()
    user_msg = data.get("content", "").strip()
    history = data.get("history", [])

    if not user_msg:
        async def empty_gen():
            yield "data: " + json.dumps({"type": "message", "content": "Please enter a message."}) + "\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    update_user_activity_streak(db)

    cmd_res = process_slash_command(user_msg, db)
    if cmd_res:
        async def cmd_gen():
            yield "data: " + json.dumps(cmd_res) + "\n\n"
        return StreamingResponse(cmd_gen(), media_type="text/event-stream")

    messages = []
    for h in history[-8:]:
        messages.append({"role": h.get("sender", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": user_msg})

    async def event_generator():
        yield "data: " + json.dumps({"type": "stream_start"}) + "\n\n"
        stream = llm_client.stream_chat(
            messages=messages,
            system_prompt=get_educator_system_prompt()
        )
        async for chunk in stream:
            if chunk["type"] == "token":
                yield "data: " + json.dumps({"type": "token", "content": chunk["content"]}) + "\n\n"
            elif chunk["type"] == "done":
                usage = chunk.get("usage", {})
                try:
                    tu = TokenUsage(
                        model=chunk.get("model", settings.MODEL_NAME),
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        operation="chat_sse"
                    )
                    db.add(tu)
                    db.commit()
                except Exception as e:
                    logger.error("Error saving token usage in SSE: %s", e)
                    db.rollback()

                yield "data: " + json.dumps({"type": "stream_end", "model": chunk.get("model"), "usage": usage}) + "\n\n"
            elif chunk["type"] == "error":
                yield "data: " + json.dumps({"type": "stream_error", "error": chunk.get("error")}) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def websocket_chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db = SessionLocal()
    try:
        await websocket.send_json({
            "type": "message",
            "sender": "assistant",
            "content": f"Hello! I am **{settings.ASSISTANT_NAME}**, your professional C# and .NET educator.\n\n"
                       f"I train you in structured sets of 25 questions, verify real mastery through teach-back and coding challenges, "
                       f"and guide you through modern C# & .NET 8/9.\n\n"
                       f"Type `/start` to begin a topic, or ask me any C# architectural question!"
        })

        while True:
            data_raw = await websocket.receive_text()
            try:
                data = json.loads(data_raw)
            except Exception:
                data = {"content": data_raw}

            user_msg = data.get("content", "").strip()
            history = data.get("history", [])

            if not user_msg:
                continue

            update_user_activity_streak(db)

            cmd_res = process_slash_command(user_msg, db)
            if cmd_res:
                await websocket.send_json(cmd_res)
                continue

            messages = []
            for h in history[-8:]:
                messages.append({"role": h.get("sender", "user"), "content": h.get("content", "")})
            messages.append({"role": "user", "content": user_msg})

            await websocket.send_json({"type": "stream_start"})

            stream = llm_client.stream_chat(
                messages=messages,
                system_prompt=get_educator_system_prompt()
            )

            async for chunk in stream:
                if chunk["type"] == "token":
                    await websocket.send_json({"type": "token", "content": chunk["content"]})
                elif chunk["type"] == "done":
                    usage = chunk.get("usage", {})
                    try:
                        tu = TokenUsage(
                            model=chunk.get("model", settings.MODEL_NAME),
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0),
                            operation="chat"
                        )
                        db.add(tu)
                        db.commit()
                    except Exception as e:
                        logger.error("Error saving token usage: %s", e)
                        db.rollback()

                    await websocket.send_json({
                        "type": "stream_end",
                        "model": chunk.get("model"),
                        "usage": usage
                    })
                elif chunk["type"] == "error":
                    await websocket.send_json({
                        "type": "stream_error",
                        "error": chunk.get("error", "Unknown LLM error occurred.")
                    })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket exception: %s", e)
        manager.disconnect(websocket)
    finally:
        db.close()
