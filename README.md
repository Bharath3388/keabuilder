# KeaBuilder — AI-Powered SaaS Platform

Production-grade AI capabilities for funnels, lead capture, and automation.

## Features

1. **AI Lead Classification** — Automatic HOT/WARM/COLD scoring with personalized responses
2. **Multi-Modal Content Router** — Unified API for image, video, and voice generation (Imagen 4.0 primary, HuggingFace fallback)
3. **LoRA Brand Kit** — Personalized AI image generation with user-trained models
4. **Similarity Search** — Face, text & CLIP similarity across asset libraries (Gemini Embedding primary, local fallback)
5. **Resilience Layer** — Circuit breakers, retries with exponential backoff, fallbacks, and degraded modes
6. **Scalable Infrastructure** — Async job queues, rate limiting, caching
7. **Security** — API key authentication, input sanitization, path traversal protection, prompt injection defense

## Tech Stack (Free / Open-Source First)

| Capability | Provider | Cost |
|---|---|---|
| LLM | Groq (Llama 3.3) / Ollama | Free |
| Image Generation | Google Imagen 4.0 (primary) / HuggingFace SDXL (fallback) | Free tier |
| Voice/TTS | edge-tts (Microsoft) + Groq script generation | Free |
| Text Embeddings | Gemini Embedding (primary) / sentence-transformers (fallback) | Free |
| Image Embeddings | Gemini Vision + Embedding (primary) / CLIP (fallback) | Free |
| Vector DB | ChromaDB | Free |
| Face Detection | InsightFace | Free |
| Job Queue | Celery + Redis | Free |
| Database | SQLite (dev) / PostgreSQL (prod) | Free |
| Orchestration | LangGraph (state machine routing) | Free |

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Configure API keys
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Docker
```bash
docker-compose up --build
```

## Configuration

Set these in `backend/.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_SECRET_KEY` | Production | Secret key (auto-generated in dev) |
| `APP_ENV` | No | `development` (default) or `production` |
| `API_KEYS` | Production | Comma-separated API keys for client auth |
| `GEMINI_API_KEY` | Recommended | Google AI key for Imagen 4.0 + Gemini embeddings |
| `GROQ_API_KEY` | Recommended | Groq key for LLM classification + voice scripts |
| `HF_API_TOKEN` | Optional | HuggingFace key (image generation fallback) |
| `CORS_ORIGINS` | No | Allowed origins (default: `http://localhost:3000`) |
| `TRUSTED_PROXIES` | No | Trusted reverse proxy IPs for rate limiting |

## Authentication

All API endpoints (except `/api/v1/health`) require an `X-API-Key` header:

```bash
curl -H "X-API-Key: your-key-here" http://localhost:8000/api/v1/assets/?workspace_id=demo
```

In **development** mode with no `API_KEYS` configured, authentication is skipped for convenience.

In **production**, set `API_KEYS` in `.env` — requests without a valid key receive `401`/`403`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/leads/classify` | Classify and respond to a lead |
| GET | `/api/v1/leads/` | List classified leads |
| POST | `/api/v1/generate` | Generate image/video/voice content |
| POST | `/api/v1/lora/train` | Start LoRA training job |
| POST | `/api/v1/lora/generate` | Generate with LoRA model |
| GET | `/api/v1/lora/list/{user_id}` | List user's LoRA models |
| POST | `/api/v1/search/similar` | Find similar assets by text |
| POST | `/api/v1/search/similar/image` | Find similar assets by image |
| GET | `/api/v1/assets/` | List workspace assets |
| POST | `/api/v1/assets/job/enqueue` | Enqueue async generation job |
| GET | `/api/v1/assets/job/{job_id}` | Check job status |
| GET | `/api/v1/health` | Health check (no auth required) |

## Database Migrations

Uses Alembic for schema migrations:

```bash
cd backend

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Security

- **API key authentication** on all endpoints (constant-time comparison)
- **Path traversal protection** — all storage paths sanitized and resolved
- **Prompt injection defense** — user inputs filtered before LLM calls
- **File upload validation** — MIME type + magic byte checks for images
- **Rate limiting** — per-IP with trusted proxy support, memory-bounded
- **CORS** — restricted origins, methods, and headers
- **Error sanitization** — internal details logged server-side, not exposed to clients
- **Storage isolation** — internal dirs (ChromaDB, LoRA weights) blocked from serving
- **S3 pre-signed URLs** — time-limited access in production
- **Non-root Docker** — containers run as unprivileged user

## Project Structure

```
backend/
├── main.py                 # FastAPI app entry point
├── config.py               # Pydantic settings with validation
├── alembic.ini             # Database migration config
├── alembic/                # Migration scripts
├── api/
│   ├── middleware/
│   │   ├── auth.py         # API key authentication
│   │   └── rate_limiter.py # Per-IP rate limiting
│   └── routes/             # API route handlers
├── models/
│   ├── database.py         # SQLAlchemy models
│   └── schemas.py          # Pydantic request/response schemas
├── services/
│   ├── provider_graph.py   # LangGraph multi-provider router
│   ├── lead_classifier.py  # LLM + rule-based classification
│   ├── response_generator.py
│   ├── similarity_search.py # Gemini/CLIP/face embeddings + ChromaDB
│   ├── lora_service.py     # LoRA training + inference
│   ├── queue_service.py    # Job queue with TTL eviction
│   └── resilience.py       # Circuit breaker + retry + fallback
├── utils/
│   ├── storage.py          # Local/S3 storage with path sanitization
│   ├── sanitize.py         # Prompt injection filtering
│   └── monitoring.py       # Prometheus metrics
└── workers/                # Celery worker definitions

frontend/
├── src/app/                # Next.js pages
└── src/lib/api.ts          # API client with retry + timeout

infra/
├── docker/                 # Dockerfiles (non-root)
└── k8s/                    # Kubernetes manifests (pinned tags)
```
