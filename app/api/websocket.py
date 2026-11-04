import json
import logging
from typing import Dict, Any, List
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import CurriculumTopic, TopicProgress, TokenUsage, UserProfile
from app.llm.client import llm_client
from app.llm.prompts import get_educator_system_prompt
from app.services.curriculum_service import update_user_activity_streak

logger = logging.getLogger("codecoach.websocket")

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

async def handle_slash_command(command_text: str, websocket: WebSocket, db: Session) -> bool:
    """
    Interprets commands: /start <topic>, /next, /hint, /skip, /explain, /progress, /links, /videos, /review
    Returns True if handled, False otherwise.
    """
    raw = command_text.strip()
    if not raw.startswith("/"):
        return False

    parts = raw.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/start":
        if not arg:
            # List available topics
            topics = db.query(CurriculumTopic).all()
            lines = [f"• `{t.id}`: {t.title}" for t in topics[:8]]
            msg = "**To begin training on a topic, use `/start <topic_id>`:**\n\n" + "\n".join(lines)
            await websocket.send_json({"type": "message", "sender": "assistant", "content": msg})
            return True

        topic = db.query(CurriculumTopic).filter(
            (CurriculumTopic.id == arg) | (CurriculumTopic.title.ilike(f"%{arg}%"))
        ).first()
        if not topic:
            await websocket.send_json({
                "type": "message",
                "sender": "assistant",
                "content": f"Topic '{arg}' was not found. Open the Roadmap sidebar to view all curriculum topics."
            })
            return True

        await websocket.send_json({
            "type": "command_action",
            "action": "start_topic",
            "topic_id": topic.id,
            "topic_title": topic.title,
            "message": f"Starting 25-question training set for **{topic.title}**."
        })
        return True

    elif cmd == "/next":
        await websocket.send_json({
            "type": "command_action",
            "action": "next_question",
            "message": "Advancing to next question..."
        })
        return True

    elif cmd == "/hint":
        await websocket.send_json({
            "type": "command_action",
            "action": "request_hint",
            "message": "Displaying hint for current question..."
        })
        return True

    elif cmd == "/skip":
        await websocket.send_json({
            "type": "command_action",
            "action": "skip_question",
            "message": "Skipping to next question..."
        })
        return True

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
        await websocket.send_json({"type": "message", "sender": "assistant", "content": msg})
        return True

    elif cmd in ("/links", "/videos"):
        await websocket.send_json({
            "type": "command_action",
            "action": "show_links",
            "message": "Opening curated official learning resources..."
        })
        return True

    elif cmd == "/review":
        await websocket.send_json({
            "type": "command_action",
            "action": "open_reviews",
            "message": "Loading questions due for spaced repetition review..."
        })
        return True

    return False

async def websocket_chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db = SessionLocal()
    try:
        # Welcome message
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

            # Update streak for active participation
            update_user_activity_streak(db)

            # Check if command
            is_cmd = await handle_slash_command(user_msg, websocket, db)
            if is_cmd:
                continue

            # Construct messages array for OpenRouter streaming
            messages = []
            for h in history[-8:]:  # keep last 8 turns for context
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
                    # Record token usage in database
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

