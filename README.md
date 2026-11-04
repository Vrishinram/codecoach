# CodeCoach - Real-Time C# & .NET Educator Chatbot

CodeCoach is a production-grade, full-stack educator platform designed to train software engineers in modern C# (.NET 8/9, C# 10-13) step-by-step. It uses the OpenRouter API for LLM streaming answers over WebSockets, trains in structured sets of 25 questions, strictly verifies genuine learning retention, and sends automated daily reminders to your device (Web Push + ntfy.sh) and email.

---

## 1. System Architecture & Tech Stack

```
                     ┌────────────────────────────────────────┐
                     │          CodeCoach PWA Client          │
                     │  (HTML5 / CSS3 / Vanilla JS / Molten)  │
                     └───────▲────────────────────────▲───────┘
                             │                        │
                   WebSocket │ Real-time Chat     HTTP│ REST API
                             ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend Server                        │
│                                                                     │
│  ┌───────────────────────┐  ┌────────────────────────────────────┐  │
│  │   LLM Client Module   │  │       Verification Service         │  │
│  │ (OpenRouter Streaming │  │ (Score / Teach-Back / Application  │  │
│  │ + Model Fallback +    │  │  Challenge / Spaced Repetition)    │  │
│  │ Exponential Backoff)  │  └────────────────────────────────────┘  │
│  └───────────────────────┘                                          │
│                                                                     │
│  ┌───────────────────────┐  ┌────────────────────────────────────┐  │
│  │ Persistent APScheduler│  │     Notification Dispatcher        │  │
│  │  (SQLAlchemy Store +  │  │ (Web Push VAPID + ntfy Fallback +  │  │
│  │   Misfire Grace Time) │──▶  Jinja2 HTML Templates via SMTP)   │  │
│  └───────────────────────┘  └────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                 SQLite Database (SQLAlchemy)                  │  │
│  │  (Curriculum, Sets, Attempts, Submissions, Tokens, Settings)  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

- **Backend**: FastAPI with async WebSocket streaming and rate limiting (`slowapi`).
- **LLM**: OpenRouter API via the `openai` SDK (`base_url="https://openrouter.ai/api/v1"`).
- **Database**: SQLite with SQLAlchemy 2.0 ORM.
- **Scheduler**: APScheduler with persistent database job store (`SQLAlchemyJobStore`) surviving application restarts.
- **Device Notifications**: Web Push (PWA) using `pywebpush` with VAPID keys, plus an optional instant `ntfy.sh` topic fallback for mobile devices.
- **Email**: `smtplib` (STARTTLS / SSL with Gmail App Password support) and Jinja2 HTML templates.
- **Frontend**: Responsive Single-Page Application (SPA) installable as a PWA (`manifest.json` + Service Worker), with light/dark mode and `highlight.js` syntax highlighting.

---

## 2. Folder Structure

```
d:\code coach\
├── .env                          # Local environment variables (git-ignored)
├── .env.example                  # Template configuration file
├── .gitignore                    # Git ignore file
├── requirements.txt              # Production and test dependencies
├── pytest.ini                    # Pytest configuration
├── README.md                     # Comprehensive documentation
├── codecoach.db                  # Persistent SQLite database
├── data/
│   ├── curriculum.json           # 6 levels, 28 topics, comprehensive C# subtopics
│   └── links.json                # Curated Microsoft Learn & official YouTube resources
├── scripts/
│   ├── generate_vapid_keys.py    # VAPID P-256 keypair generator
│   └── seed_data.py              # CLI seed script for curriculum and links
├── app/
│   ├── __init__.py
│   ├── config.py                 # Pydantic Settings management
│   ├── database.py               # Engine, SessionLocal, Base
│   ├── models.py                 # SQLAlchemy relational schema
│   ├── schemas.py                # Pydantic DTOs and API schemas
│   ├── main.py                   # FastAPI initialization and middleware
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py             # OpenRouter client, retry, backoff, model fallback
│   │   ├── prompts.py            # Professional educator prompts & grading rubrics
│   │   └── grader.py             # Validated JSON grading and token tracking
│   ├── services/
│   │   ├── __init__.py
│   │   ├── curriculum_service.py # Unlocking logic and topic mastery evaluation
│   │   ├── quiz_service.py       # 25-question sets, attempts, consecutive correct
│   │   ├── verification_service.py # 4-step Learning Verification workflow
│   │   ├── reminder_service.py   # Smart reminders, comeback nudge, celebrations
│   │   ├── push_service.py       # Web Push (VAPID) and ntfy.sh delivery
│   │   ├── email_service.py      # smtplib email dispatcher with Jinja2
│   │   ├── link_validator.py     # HTTP URL validation and user custom links
│   │   └── scheduler_service.py  # Persistent APScheduler with misfire catch-up
│   ├── api/
│   │   ├── __init__.py
│   │   ├── websocket.py          # WebSocket chat streaming and slash commands
│   │   ├── routes_quiz.py        # Sets, attempts, placement test, verification
│   │   ├── routes_progress.py    # Dashboard stats, curriculum roadmap, links
│   │   ├── routes_notifications.py# Push subscription and test endpoints
│   │   └── routes_settings.py    # User configuration and preferences
│   └── templates/
│       └── email/
│           ├── daily_reminder.html
│           ├── weekly_summary.html
│           ├── comeback_nudge.html
│           └── celebration.html
├── static/
│   ├── index.html                # Single-page application UI
│   ├── manifest.json             # PWA Web App Manifest
│   ├── css/
│   │   └── style.css             # Light & Dark theme stylesheet
│   ├── js/
│   │   ├── app.js                # Routing, theme toggle, push subscription
│   │   ├── chat.js               # WebSocket streaming, syntax highlighter
│   │   ├── quiz.js               # 25-Q sets, evaluation, modals, placement
│   │   ├── dashboard.js          # Stats, charts, roadmap, custom links
│   │   └── sw.js                 # PWA Service Worker (push notifications & deep links)
│   └── icons/
│       ├── icon.svg              # Scalable vector logo
│       ├── icon-192.png          # 192x192 PWA icon
│       └── icon-512.png          # 512x512 PWA icon
└── tests/
    ├── conftest.py               # In-memory DB and test fixtures
    ├── test_scoring_mastery.py   # Scoring, unlock & mastery tests
    ├── test_spaced_repetition.py # 1d, 3d, 7d spaced repetition tests
    ├── test_scheduler_and_reminders.py # Scheduler & quiet hours tests
    ├── test_push_and_email.py    # Push & email senders tests
    └── test_llm_client_and_grader.py # LLM client, retry, backoff & JSON tests
```

---

## 3. Database Schema

The database consists of 12 tables:

1. **`curriculum_levels`**: `id`, `title`, `order`, `description`.
2. **`curriculum_topics`**: `id`, `level_id`, `title`, `order`, `description`, `subtopics_json`.
3. **`topic_progress`**: Tracks progression: `status` (`New`, `Learning`, `Reviewing`, `Mastered`), `sets_completed`, `highest_score`, `latest_score`, `teach_back_passed`, `teach_back_score`, `app_challenge_passed`, `app_challenge_score`, `retention_stage` (0 to 3), `next_retention_due_at`, `unlocked`.
4. **`quiz_sets`**: `id`, `topic_id`, `set_number`, `is_retry_set`, `total_questions`, `score`, `passed`, `completed`, `weak_subtopics_json`, `created_at`.
5. **`quiz_questions`**: `id`, `set_id`, `topic_id`, `question_index`, `question_type` (`mcq`, `output_prediction`, `fill_blank`, `coding`), `prompt`, `code_snippet`, `options_json`, `correct_answer`, `explanation`, `hint`, `difficulty` (1 to 5), `subtopic`.
6. **`question_attempts`**: `id`, `question_id`, `topic_id`, `user_answer`, `is_correct`, `consecutive_correct` (must reach 2 to clear), `needs_review`, `attempted_at`.
7. **`teach_back_submissions`**: `id`, `topic_id`, `student_explanation`, `accuracy_score`, `completeness_score`, `clarity_score`, `overall_score`, `missing_points_json`, `feedback`, `passed`, `created_at`.
8. **`application_challenge_submissions`**: `id`, `topic_id`, `prompt`, `student_code`, `score`, `correctness_notes`, `edge_case_notes`, `style_notes`, `feedback`, `passed`, `created_at`.
9. **`retention_quizzes`**: `id`, `topic_id`, `stage` (1=1d, 2=3d, 3=7d), `due_at`, `completed_at`, `score`, `passed`.
10. **`learning_links`**: `id`, `topic_id`, `title`, `url`, `type` (`article`/`video`), `level`, `is_active`, `is_custom`, `is_completed`, `last_checked_at`.
11. **`push_subscriptions`**: `id`, `endpoint`, `p256dh`, `auth`, `user_agent`, `created_at`.
12. **`notification_logs`**: `id`, `channel` (`push`/`email`/`ntfy`), `notification_type`, `subject`, `content`, `status` (`sent`/`failed`), `error_message`, `sent_at`.
13. **`token_usage`**: `id`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `operation`, `created_at`.
14. **`user_profile`**: `current_streak`, `longest_streak`, `last_active_date`, `placement_completed`, `placement_score`, `push_enabled`, `email_enabled`, `ntfy_enabled`, `reminders_paused`, `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`, `reminder_times`.
15. **`apscheduler_jobs`**: Managed automatically by APScheduler SQLAlchemyJobStore.

---

## 4. Setup Steps

### 4.1. Clone and Set Up Virtual Environment

#### On Windows (PowerShell):
```powershell
cd "d:\code coach"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### On macOS / Linux:
```bash
cd "/path/to/code coach"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### 4.2. Obtaining an OpenRouter API Key
1. Go to [https://openrouter.ai/](https://openrouter.ai/) and create an account.
2. Navigate to **Keys** -> **Create Key**.
3. Copy the key (starts with `sk-or-v1-...`).
4. Paste it into your `.env` file under `OPENROUTER_API_KEY`.

---

### 4.3. Obtaining a Gmail App Password
1. Sign in to your Google Account and visit [Google Account Security](https://myaccount.google.com/security).
2. Ensure **2-Step Verification** is turned **ON**.
3. In the search box at the top, type **App passwords** and click on it.
4. Name the app `CodeCoach` and click **Create**.
5. Copy the 16-character generated password (e.g. `abcd efgh ijkl mnop`).
6. Paste into your `.env`:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop
   EMAIL_FROM=CodeCoach <your_email@gmail.com>
   USER_EMAIL=your_email@gmail.com
   ```

---

### 4.4. Generating VAPID Keys for Web Push
Run the provided generator:
```powershell
python scripts/generate_vapid_keys.py
```
This generates standard base64url-encoded P-256 keys:
```env
VAPID_PUBLIC_KEY=BJFi_V38NQ3ZQqaPGkMEc9BDQqWLzamXjfm5eRgpsTNs_4RY6FwwzccXdkW-mXOoeL5D8mZdRLdp4doDsKQ59vU
VAPID_PRIVATE_KEY=NLJc_Un9D6LBfa8sMG0vyxG0C-e-C5V87_Tmx3-dcLc
VAPID_SUBJECT=mailto:your_email@gmail.com
```

---

### 4.5. Enabling Notifications on Your Phone

#### Option A: Web Push PWA (Chrome / Safari / Edge)
1. Open your browser on your phone and navigate to your `APP_URL` (e.g. `http://<your-lan-ip>:8000` or your deployed HTTPS URL).
2. Tap the browser menu and select **Add to Home screen** / **Install CodeCoach**.
3. Open the installed app and tap the bell icon (`🔔`) in the top navigation bar.
4. Allow notification permissions when prompted.
5. In the **Settings** tab, tap **Send Test Push** to verify.

#### Option B: ntfy.sh Instant Mobile Push (Zero Config Fallback)
1. Install the free **ntfy** app from Google Play or Apple App Store.
2. Open ntfy and tap **Subscribe to topic**.
3. Enter your private topic name (e.g. `codecoach_alice_csharp_9281`).
4. In your `.env`, set:
   ```env
   NTFY_TOPIC=codecoach_alice_csharp_9281
   ```
5. All reminders will now arrive as native push alerts on your phone without requiring HTTPS or browser service workers!

---

### 4.6. Seed Data and Run Command

```powershell
# 1. Seed curriculum and links
python scripts/seed_data.py

# 2. Run test suite
pytest -v

# 3. Start development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to `http://localhost:8000`.

---

## 5. Sample Reminder Content

### Sample Push Notification
```
Title: CodeCoach: Daily C# Training
Body:  Today: Classes, Records & Objects • Set #1 ready to train (🔥 4d Streak)
Action: [Open Training] -> Navigates directly to http://localhost:8000/#quiz/classes-and-objects
```

### Sample HTML Email Subject & Body
```
Subject: C# Daily Reminder: Classes, Records & Objects (4 Day Streak)

Header: CodeCoach • C# & .NET Educator | 🔥 4 Day Streak
Message:
Consistency is the foundation of senior engineering mastery. Here is your targeted C# curriculum schedule for today:

TODAY'S FOCUS:
Classes, Records & Objects
Set #1 ready to train

SPACED REPETITION DUE:
🧠 1 Delayed Retention Quiz Due for Variables & Data Types
Passing spaced repetition at 1, 3, and 7 days confirms long-term memory and locks in your "Mastered" status.

RECOMMENDED READING & VIDEO:
- [ARTICLE] Classes, Structs, and Records - Microsoft Learn
- [VIDEO] C# Records Explained - Nick Chapsas

[Launch Today's Session ->]
```

---

## 6. How to Customize Settings

All core behaviors can be adjusted in `.env` or dynamically in the UI:

| Parameter | Default | Purpose |
|---|---|---|
| `REMINDER_TIMES` | `08:00,20:00` | Comma-separated 24-hour reminder schedule in local time |
| `SET_SIZE` | `25` | Questions per topic set (10 MCQ, 5 Output, 5 Fill-blank, 5 Coding) |
| `PASS_SCORE` | `70` | Minimum score to pass a set and unlock Step 2 (Teach-Back) |
| `MASTERY_SCORE` | `85` | Score required on set, teach-back, coding challenge, and all retention checks to achieve "Mastered" |
| `TIMEZONE` | `Asia/Kolkata` | Timezone evaluated by APScheduler for cron triggers |
| `ASSISTANT_NAME` | `CodeCoach` | Name rendered in UI, emails, and LLM system prompts |

---

## 7. Keeping the App Running 24/7 (Persistent Reminders)

### Option 1: Docker Compose (Cross-Platform)

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  codecoach:
    build: .
    container_name: codecoach_app
    restart: always
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./codecoach.db:/app/codecoach.db
```

Dockerfile:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/seed_data.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Run:
```bash
docker compose up -d
```

### Option 2: Linux systemd Service
Create `/etc/systemd/system/codecoach.service`:
```ini
[Unit]
Description=CodeCoach C# Educator Chatbot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/codecoach
ExecStart=/home/ubuntu/codecoach/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now codecoach
```

### Option 3: Windows Background Service (NSSM)
```powershell
nssm install CodeCoach "d:\code coach\venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
nssm set CodeCoach AppDirectory "d:\code coach"
nssm start CodeCoach
```

---

## 8. Troubleshooting Guide

### 1. HTTP 401 Unauthorized (OpenRouter)
- **Cause**: The `OPENROUTER_API_KEY` in `.env` is incorrect or unset.
- **Fix**: Open `.env` and verify your key starts with `sk-or-v1-`. Restart the server.

### 2. HTTP 402 Payment Required (OpenRouter)
- **Cause**: Your OpenRouter account balance has run out.
- **Fix**: Visit [https://openrouter.ai/credits](https://openrouter.ai/credits) and top up your account.

### 3. HTTP 429 Rate Limit
- **Behavior**: CodeCoach automatically catches 429 errors, executes exponential backoff (2s, 4s), and automatically switches to the next fallback model in `FALLBACK_MODELS`.
- **Customization**: Update `FALLBACK_MODELS` in `.env` to include fast, generous models (e.g. `google/gemini-2.0-flash-001,openai/gpt-4o-mini,meta-llama/llama-3.3-70b-instruct`).

### 4. SMTP Authentication Errors (Gmail)
- **Cause**: Using regular Gmail account password instead of an App Password.
- **Fix**: Enable 2FA on Google Account and generate a 16-character App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Ensure `SMTP_PORT=587`.

### 5. Web Push Notification Not Arriving
- **Cause**: Browser permissions not granted, or expired VAPID token.
- **Fix**: Click the bell icon (`🔔`) in the navbar. Alternatively, configure `NTFY_TOPIC` in `.env` for instant push notifications to any phone via the free ntfy mobile app.

### 6. Invalid JSON from LLM
- **Behavior**: CodeCoach does not rely on provider JSON mode; instead, `app/llm/client.py` strips markdown wrappers and performs an automated correction retry if the output fails JSON decoding. Tested and verified in `tests/test_llm_client_and_grader.py`.

