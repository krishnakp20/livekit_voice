# VBots – AI Voice Calling SaaS Platform

Production-grade multi-tenant AI voice calling platform with FastAPI, React, MySQL, Redis, LiveKit SIP, OpenAI/Sarvam, VICIdial, and WhatsApp integrations.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   React UI  │────▶│  FastAPI API │────▶│     MySQL       │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌─────────┐  ┌──────────┐
         │ Redis  │  │ Celery  │  │ LiveKit  │
         └────────┘  └─────────┘  │   SIP    │
                                  └────┬─────┘
                                       ▼
                              ┌─────────────────┐
                              │ Agent Runtime   │
                              │ Worker (dynamic)│
                              └─────────────────┘
```

### Key Components

| Component | Path | Purpose |
|-----------|------|---------|
| API Server | `backend/app/main.py` | REST API, JWT auth, WebSocket |
| Agent Worker | `backend/worker/agent_runtime.py` | Dynamic multi-agent call handling |
| LiveKit Agent | `backend/worker/livekit_agent.py` | LiveKit Agents SDK integration |
| Celery | `backend/app/tasks/` | Campaign dialing, WhatsApp reports |
| Frontend | `frontend/src/` | Enterprise UI for non-technical users |

## Features

- **Multi-tenant SaaS** – Clients, RBAC (super_admin, client_admin, manager, agent, viewer)
- **AI Agent Builder** – Prompt, language (Hindi/English/Hinglish), voice, greeting, fallback, business hours
- **SIP Trunk Management** – Inbound/outbound, DID assignment, LiveKit auto-provisioning
- **Dispatch Mapping** – DID, trunk, campaign, ingroup → agent
- **Live Call Dashboard** – Real-time transcripts, sentiment, speaking indicators
- **Campaigns & Leads** – CSV upload, retry logic, scheduled dialing
- **VICIdial Integration** – Lead sync, disposition, webhooks
- **WhatsApp** – Call summaries, missed calls, daily reports
- **Analytics** – Conversion rate, AHT, AI latency, agent performance

## Quick Start (Docker)

### Prerequisites

- Docker & Docker Compose
- (Optional) OpenAI and/or Sarvam API keys
- (Optional) WhatsApp Cloud API credentials

### 1. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set at minimum:

```env
SECRET_KEY=<generate-with-openssl-rand-hex-32>
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
OPENAI_API_KEY=sk-...
SARVAM_API_KEY=...
```

### 2. Start all services

```bash
docker compose up -d --build
```

### 3. Access the platform

| Service | URL |
|---------|-----|
| Web UI (via nginx) | http://localhost |
| Frontend direct | http://localhost:5173 |
| API / Swagger docs | http://localhost:8000/docs |
| LiveKit | ws://localhost:7880 |

### 4. Demo login

```
Email:    admin@demo.com
Password: admin123
```

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env

# Start MySQL & Redis (or use docker compose up mysql redis -d)
uvicorn app.main:app --reload --port 8000

# Seed demo data
cd backend
python scripts/seed.py

# LiveKit voice agent worker (see "Run the AI agent" below)
pip install -r requirements-agents.txt
python worker/agent.py dev

# Celery
celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (API proxied to :8000).

## Database (MySQL 8)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async driver: `mysql+aiomysql://user:pass@host:3306/vbots?charset=utf8mb4` |
| `DATABASE_URL_SYNC` | Sync driver (Alembic/Celery): `mysql+pymysql://...` |

Docker exposes MySQL on port **3306**. If you previously used PostgreSQL, remove the old volume: `docker volume rm vbots_postgres_data`.

Migrations:

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Agent Configuration Example

```json
{
  "name": "Priya Sales Agent",
  "language": "hi-IN",
  "voice": "simran",
  "provider": "sarvam",
  "model": "gpt-4o-mini",
  "prompt": "You are a friendly Indian sales agent.",
  "greeting": "Namaste! Kaise madad kar sakti hoon?",
  "fallback_message": "Maaf kijiye, dobara batayenge?",
  "temperature": 0.6,
  "max_tokens": 120,
  "interruptions_enabled": true,
  "record_calls": true,
  "transfer_enabled": true
}
```

## Run the AI agent (LiveKit worker)

VBots uses **one worker process** for all calls. Each call gets the correct agent from the database (not a separate `agent.py` per DID).

### Architecture

```
Inbound call → SIP trunk → LiveKit dispatch rule → room agent-{id}-xxx
                                                      ↓
                                            worker/agent.py (JobContext)
                                                      ↓
                                            load ai_agents row from MySQL
                                                      ↓
                                            Sarvam STT + OpenAI LLM + Sarvam TTS
```

### Per-DID routing (different agents per number)

1. Create **multiple AI agents** in the UI (e.g. Sales, Support).
2. **Dispatch Rules** → type **DID** → match value = phone number (e.g. `918012345678`) → pick agent → link SIP trunk.
3. Each DID rule creates a LiveKit dispatch rule with `agent_id` in metadata.
4. Run the worker (below). It reads `agent_id` from room metadata or `dispatch_rules` table.

### Start the worker (Windows)

```powershell
cd backend
.\.venv\Scripts\activate
pip install -r requirements-agents.txt

# Same .env as API — required:
# LIVEKIT_URL=ws://192.168.10.30:7880
# LIVEKIT_API_KEY=...
# LIVEKIT_API_SECRET=...
# OPENAI_API_KEY=...
# SARVAM_API_KEY=...
# DATABASE_URL=mysql+aiomysql://...

python worker/agent.py dev
```

Use `python worker/agent.py start` in production.

### Migrate your existing agent.py

Your standalone `agent.py` (Priya + Sarvam + Silero) is integrated in `backend/worker/agent.py`. It loads **prompt, greeting, voice, language** from the `ai_agents` table instead of hardcoded `SYSTEM_PROMPT`.

Optional env:

```env
VBOT_RECORDING_ENABLED=true
VBOT_RECORDINGS_DIR=./recordings
```

### Three services must run

| Service | Command |
|---------|---------|
| API | `uvicorn app.main:app --reload --port 8000` |
| Frontend | `npm run dev` (in `frontend/`) |
| **Agent worker** | `python worker/agent.py dev` |

## LiveKit SIP Flow

1. User creates SIP trunk in UI → API provisions LiveKit inbound trunk
2. User creates dispatch rule (DID → Agent) → API creates LiveKit dispatch rule with agent metadata
3. Inbound call hits SIP → LiveKit creates room → Worker loads agent config from DB
4. Outbound: `POST /api/v1/calls/outbound` → creates room + dials via SIP participant

## API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/login` | JWT login |
| `GET/POST /api/v1/agents` | AI agent CRUD |
| `POST /api/v1/agents/{id}/test` | Prompt playground |
| `GET/POST /api/v1/sip-trunks` | SIP trunk management |
| `POST /api/v1/sip-trunks/{id}/test` | Test connectivity |
| `GET/POST /api/v1/dispatch` | Dispatch rules |
| `GET/POST /api/v1/campaigns` | Campaigns |
| `POST /api/v1/leads/upload` | CSV lead import |
| `GET /api/v1/calls/live` | Active calls |
| `GET /api/v1/analytics/dashboard` | Analytics |
| `POST /api/v1/webhooks/livekit` | LiveKit events |
| `POST /api/v1/webhooks/vicidial/{client_id}` | VICIdial webhooks |

## WebSocket Events

Connect to `/ws/socket.io` with `auth: { client_id: <id> }`.

| Event | Description |
|-------|-------------|
| `call_update` | Call status changes |
| `transcript` | Real-time transcript streaming |
| `sentiment` | Sentiment score updates |

## Production Deployment

1. Set strong `SECRET_KEY` and rotate API keys
2. Use managed MySQL 8+ and Redis
3. Deploy LiveKit server with proper `use_external_ip` and TLS
4. Configure SIP provider trunks pointing to LiveKit SIP
5. Set `CORS_ORIGINS` to your domain
6. Use nginx TLS termination (add certbot/Let's Encrypt)
7. Scale workers: `docker compose up --scale worker=3`

### Environment variables (production)

See `backend/.env.example` for the full list.

## Project Structure

```
vbots/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/    # REST endpoints
│   │   ├── core/             # Config, security, deps
│   │   ├── db/models/        # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # LiveKit, AI, WhatsApp, VICIdial
│   │   ├── tasks/            # Celery tasks
│   │   └── websocket/        # Socket.IO
│   ├── worker/               # Agent runtime + LiveKit agent
│   └── scripts/seed.py
├── frontend/
│   └── src/pages/            # All UI pages
├── infra/
│   ├── livekit.yaml
│   └── nginx.conf
└── docker-compose.yml
```

## License

Proprietary – All rights reserved.
