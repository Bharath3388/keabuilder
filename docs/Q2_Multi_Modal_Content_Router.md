# Q2: Multi-Modal Content Generation Router

## Design Overview

KeaBuilder uses a **LangGraph state machine** to route content generation requests to the correct AI provider based on media type. Each provider is encapsulated as a graph node, and a shared `store_asset` node handles output persistence.

```
┌─────────────────┐
│  API Request     │  POST /api/v1/generate
│  { type, prompt }│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LangGraph       │  _route_by_media_type()
│  Entry Point     │
└───┬─────┬────┬──┘
    │     │    │
    ▼     ▼    ▼
┌──────┐ ┌──────┐ ┌──────┐
│image │ │voice │ │video │
│_node │ │_node │ │_node │
└──┬───┘ └──┬───┘ └──┬───┘
   │        │        │
   ▼        ▼        ▼
┌─────────────────────────┐
│     store_asset_node     │  Save to local/S3 storage
└────────────┬────────────┘
             │
             ▼
          END → Return asset_id, url, provider_used
```

**Implementation:** `backend/services/provider_graph.py`

---

## Routing Logic

### How It Works

The `GenerateRequest` schema requires a `type` field (`image`, `video`, or `voice`). The LangGraph state machine uses a **conditional entry point** that inspects `state["media_type"]` and routes to the appropriate provider node:

```python
def _route_by_media_type(state: ContentState) -> str:
    media_type = state["media_type"]
    if media_type == "image":
        return "image_node"
    elif media_type == "voice":
        return "voice_node"
    elif media_type == "video":
        return "video_node"
```

### Provider Mapping

| Media Type | Primary Provider | Fallback Provider | Output Format |
|------------|-----------------|-------------------|---------------|
| **Image** | Google Imagen 4.0 | HuggingFace SDXL → Placeholder | PNG |
| **Voice** | Groq LLM (script) + edge-tts (synthesis) | Raw prompt + edge-tts | MP3 |
| **Video** | Gemini 2.0 Flash (storyboard) | Groq LLM storyboard → Placeholder JSON | JSON |

### Image Node

```
User Prompt
    │
    ▼
┌────────────────┐    success    ┌──────────────┐
│ Imagen 4.0     │──────────────▶│ Return PNG   │
│ (Google)       │               └──────────────┘
└───────┬────────┘
        │ failure
        ▼
┌────────────────┐    success    ┌──────────────┐
│ HuggingFace    │──────────────▶│ Return PNG   │
│ SDXL           │               └──────────────┘
└───────┬────────┘
        │ failure
        ▼
┌────────────────┐
│ Placeholder    │  (Pillow-generated image with prompt text)
│ Generator      │
└────────────────┘
```

The primary→fallback chain uses the resilience layer's `call_with_fallback()` with circuit breaker protection.

### Voice Node (Two-Stage Pipeline)

```
User Prompt
    │
    ▼
┌────────────────┐
│ Groq LLM       │  "Convert this description into a polished voiceover script"
│ Script Writer   │
└───────┬────────┘
        │ polished script (or raw prompt on failure)
        ▼
┌────────────────┐
│ edge-tts       │  Microsoft's free TTS engine
│ Synthesizer    │
└───────┬────────┘
        │
        ▼
    MP3 audio bytes
```

### Video Node

Since no free video generation API exists, the video node generates a **professional storyboard JSON** using Gemini 2.0 Flash (or Groq fallback) that includes scene descriptions, camera angles, voiceover scripts, and music mood — ready to feed into Runway ML, Pika Labs, or similar tools.

---

## Frontend ↔ Backend Interaction

### Request Flow

```
┌──────────────────┐          ┌──────────────────┐          ┌─────────────┐
│  Builder UI      │  POST    │  FastAPI Backend  │  invoke  │  LangGraph  │
│  (Next.js)       │─────────▶│  /api/v1/generate │─────────▶│  State      │
│                  │          │                  │          │  Machine    │
│  GenerateRequest │          │  Auth + Validate │          │             │
│  {type, prompt,  │          │  + Rate Limit    │          │  image_node │
│   workspace_id}  │          │                  │          │  voice_node │
└──────────────────┘          └──────────────────┘          │  video_node │
                                                            └──────┬──────┘
                                                                   │
       ┌───────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────┐          ┌──────────────────┐
│  Store Asset     │  persist │  SQLite / PG     │
│  (local / S3)    │─────────▶│  AssetRecord     │
└──────────────────┘          └──────────────────┘
       │
       ▼
┌──────────────────┐
│  Auto-Index      │  ChromaDB text + CLIP embeddings
│  for Search      │  (for similarity search in Q4)
└──────────────────┘
```

**Frontend API call** (from `frontend/src/lib/api.ts`):

```typescript
export async function generateContent(req: GenerateRequest) {
  return apiCall("/generate", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
```

The frontend sends a single unified request. The backend handles all routing internally — the UI never needs to know which AI provider is being used.

---

## How Outputs Are Managed Inside the Platform

### 1. Storage

Generated assets are saved to the configured storage backend:
- **Development**: Local filesystem at `./storage/{workspace_id}/{type}/{asset_id}.{ext}`
- **Production**: S3 with pre-signed URLs (1-hour expiry)

### 2. Database Record

Every generated asset creates an `AssetRecord` row:

```python
AssetRecord(
    id="ast_20260424_image_a3f1b2c0",
    workspace_id="demo_workspace",
    user_id="user_123",
    type="image",
    url="/storage/demo_workspace/images/ast_20260424_image_a3f1b2c0.png",
    prompt="A modern SaaS landing page hero image",
    prompt_hash="3a7f2b...",     # SHA-256 for dedup/caching
    provider="imagen-4.0",
    style="photorealistic",
    width=1024,
    height=1024,
    size_bytes=524288,
    tags=[],
    created_at="2026-04-24T10:30:00Z"
)
```

### 3. Auto-Indexing for Search

After generation, every asset is automatically indexed into ChromaDB:
- **Text embedding** — prompt text is embedded for text-to-asset search
- **CLIP embedding** — images are additionally embedded for image-to-image similarity search

### 4. Asset Listing API

The `GET /api/v1/assets/` endpoint provides paginated, filterable access to all workspace assets:

```
GET /api/v1/assets/?workspace_id=demo_workspace&type=image&page=1&page_size=20
```

### Sample Generate Request → Response

**Request:**
```json
{
  "type": "image",
  "prompt": "A modern SaaS landing page hero image with abstract gradients",
  "style": "photorealistic",
  "dimensions": { "width": 1024, "height": 1024 },
  "user_id": "user_123",
  "workspace_id": "demo_workspace"
}
```

**Response:**
```json
{
  "asset_id": "ast_20260424_image_a3f1b2c0",
  "status": "completed",
  "url": "/storage/demo_workspace/images/ast_20260424_image_a3f1b2c0.png",
  "provider_used": "imagen-4.0",
  "metadata": {
    "type": "image",
    "dimensions": { "width": 1024, "height": 1024 },
    "size_bytes": 524288,
    "created_at": "2026-04-24T10:30:00Z"
  },
  "script": null
}
```

**Voice Response (with generated script):**
```json
{
  "asset_id": "ast_20260424_voice_f7e2a901",
  "status": "completed",
  "url": "/storage/demo_workspace/voice/ast_20260424_voice_f7e2a901.mp3",
  "provider_used": "groq+edge-tts",
  "metadata": {
    "type": "voice",
    "size_bytes": 98304,
    "created_at": "2026-04-24T10:31:00Z"
  },
  "script": "Welcome to Acme Corp, where innovation meets simplicity. Our platform helps you build, launch, and scale your business — all in one place."
}
```
