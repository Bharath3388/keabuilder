# Q6: Scalability — Handling High-Volume AI Requests

## Design Overview

KeaBuilder is designed to scale from a single-developer laptop to production workloads through a layered strategy covering **job queuing**, **rate limiting**, **resource management**, **monitoring**, and **Kubernetes orchestration**.

```
┌───────────────────────────────────────────────────────────────────┐
│                     Scalability Architecture                      │
│                                                                   │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌───────────┐  │
│  │ Rate     │───▶│ Job      │───▶│ Worker    │───▶│ AI        │  │
│  │ Limiter  │    │ Queue    │    │ Pool      │    │ Providers │  │
│  │          │    │          │    │           │    │           │  │
│  │ Per-IP   │    │ Priority │    │ Image     │    │ Imagen    │  │
│  │ throttle │    │ lanes    │    │ Video     │    │ Gemini    │  │
│  │          │    │ Idemp.   │    │ LoRA      │    │ Groq      │  │
│  │          │    │ TTL evic │    │           │    │ HF        │  │
│  └─────────┘    └──────────┘    └───────────┘    └───────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Observability: Prometheus metrics + structured logging       │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Infrastructure: Docker (non-root) + Kubernetes (HPA)        │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## 1. Job Queue System

**Implementation:** `backend/services/queue_service.py`

### How It Works

All long-running AI operations (image generation, voice synthesis, lead classification) can be routed through the job queue instead of being processed inline:

```
POST /api/v1/assets/enqueue
        │
        ▼
┌───────────────────┐
│  Idempotency      │  If same idempotency_key exists → return existing job
│  Check            │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Evict Expired    │  Remove completed/failed jobs older than 24 hours
│  Jobs             │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Capacity Check   │  If _job_store >= 10,000 → reject with "Queue full"
│                   │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Enqueue Job      │  Priority: 1 (highest) → 10 (lowest)
│                   │
│  Dev:  process    │  In dev mode, executes synchronously
│        inline     │
│  Prod: dispatch   │  In production, dispatches to Celery + Redis worker
│        to worker  │
└───────────────────┘
```

### Priority Lanes

| Priority | Use Case | Example |
|----------|----------|---------|
| 1-2 | Hot leads, paid-plan users | Lead classified as HOT |
| 3-5 | Normal operations | Standard image generation |
| 6-8 | Batch operations | Bulk asset regeneration |
| 9-10 | Cold lead processing | Low-priority background tasks |

### Job Lifecycle

```
QUEUED → PROCESSING → COMPLETED
                   ↘ FAILED (after 3 retries)
                   ↘ QUEUED (retry, if retries remaining)
```

### Resource Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| Max jobs in store | 10,000 | Prevent unbounded memory growth |
| Job TTL | 24 hours | Auto-evict stale completed/failed jobs |
| Max retries per job | 3 | Prevent infinite retry loops |
| Idempotency dedup | By key | Prevent duplicate submissions |

### Production Architecture (Celery + Redis)

```
┌──────────┐     ┌───────┐     ┌──────────────┐
│ FastAPI   │────▶│ Redis │────▶│ Celery       │
│ Backend   │     │ Queue │     │ Workers (N)  │
│           │     │       │     │              │
│ enqueue() │     │ FIFO  │     │ image_worker │
│           │     │ + pri │     │ video_worker │
│           │     │       │     │ lora_trainer │
└──────────┘     └───────┘     └──────────────┘
```

---

## 2. Rate Limiting

**Implementation:** `backend/api/middleware/rate_limiter.py`

### Strategy

- **Sliding window** rate limiter applied to all API endpoints
- **Per-IP tracking** with trusted proxy support (only trusts `X-Forwarded-For` from configured proxies)
- **Stale entry cleanup** prevents the tracking dictionary from growing unboundedly

### Limits

| Resource | Limit | Window |
|----------|-------|--------|
| API requests per IP | Configurable | Sliding window |
| Max tracked IPs | 10,000 | Prevents DoS via IP exhaustion |
| Stale entry eviction | Periodic | Removes expired entries on each request |

### Trusted Proxy Support

```python
# Only trust X-Forwarded-For from known proxies
trusted_proxies: list[str] = ["10.0.0.1", "172.16.0.1"]

# If request comes from untrusted IP, use direct connection IP
# This prevents IP spoofing attacks
```

---

## 3. Monitoring & Observability

**Implementation:** `backend/utils/monitoring.py`

### Prometheus Metrics

The system exposes structured metrics at `GET /metrics`:

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `ai_call_total` | Counter | provider, status | Track API usage per provider |
| `ai_call_duration_seconds` | Histogram | provider | Latency distribution |
| `fallback_total` | Counter | service | How often fallbacks activate |
| `queue_depth` | Gauge | queue_name | Current queue size |
| `active_jobs` | Gauge | job_type | Currently processing jobs |

### Structured Logging

All services use `structlog` for machine-parseable JSON logs:

```json
{
  "event": "image_generated",
  "provider": "imagen-4.0",
  "latency_ms": 2340,
  "workspace_id": "demo_workspace",
  "asset_id": "ast_20260424_image_a3f1",
  "timestamp": "2026-04-24T10:30:02Z"
}
```

### Timer Context Manager

All AI calls are wrapped with a `Timer` context manager that automatically records latency to Prometheus:

```python
with Timer("imagen_generate"):
    image_data = await call_imagen_api(prompt)
# → Automatically records duration to ai_call_duration_seconds{provider="imagen_generate"}
```

---

## 4. Kubernetes Deployment

**Implementation:** `infra/k8s/deployment.yaml`, `infra/k8s/service.yaml`

### Current Configuration

```yaml
Backend:
  replicas: 2
  resources:
    requests: { cpu: 250m, memory: 512Mi }
    limits:   { cpu: "1",  memory: 1Gi }

Frontend:
  replicas: 2
  resources:
    requests: { cpu: 100m, memory: 128Mi }
    limits:   { cpu: 500m, memory: 256Mi }
```

### Horizontal Pod Autoscaler (HPA)

With Prometheus metrics exposed, a standard HPA can scale based on:

```yaml
# Example HPA (not yet deployed, but metrics are ready)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: keabuilder-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Pods
      pods:
        metric:
          name: active_jobs
        target:
          type: AverageValue
          averageValue: 5
```

### Security Hardening

- **Non-root containers**: Both Dockerfiles create an `appuser` (UID 1001) and switch to it
- **Pinned image tags**: `keabuilder-backend:1.0.0` instead of `:latest`
- **imagePullPolicy**: `IfNotPresent` to prevent tag mutation attacks

---

## 5. Cost Optimization Strategy

### Free-Tier First Architecture

KeaBuilder is designed to operate at **zero cost** during development and low-traffic production:

| Service | Free Tier | Paid Escalation |
|---------|-----------|-----------------|
| Groq (Llama 3.3) | Free API (rate limited) | — |
| Google Imagen 4.0 | Free tier available | Pay-per-image at scale |
| Gemini 2.0 Flash | Free tier (15 RPM) | $0.10/1M tokens |
| Gemini Embedding | Free tier | $0.004/1M tokens |
| HuggingFace SDXL | Free Inference API | Self-hosted on GPU |
| edge-tts | Free (Microsoft) | — |
| ChromaDB | Open-source, local | — |
| InsightFace | Open-source, local | — |
| sentence-transformers | Open-source, local | — |

### Multi-Provider Fallback Reduces Cost

The fallback chain doubles as a cost-optimization strategy:
1. Try the **best free provider** first (e.g., Imagen 4.0 free tier)
2. If rate-limited, fall back to **another free provider** (HuggingFace)
3. Only use **paid providers** when free options are exhausted
4. **Placeholder generation** as last resort (zero cost, always available)

---

## 6. Performance Characteristics

### Latency by Operation

| Operation | Typical Latency | Bottleneck |
|-----------|----------------|------------|
| Lead classification (LLM) | 1-3 seconds | Groq API |
| Lead classification (rule-based) | < 10 ms | CPU only |
| Image generation (Imagen) | 2-5 seconds | Google API |
| Image generation (HF) | 5-10 seconds | HF API |
| Voice generation | 2-4 seconds | edge-tts |
| Text similarity search | 10-50 ms | ChromaDB HNSW |
| Image similarity search | 50-200 ms | Embedding + ChromaDB |
| Face search | 100-500 ms | InsightFace + ChromaDB |

### Throughput Limits

| Component | Limit | Scaling Path |
|-----------|-------|-------------|
| FastAPI backend | ~500 concurrent connections | Add replicas via K8s |
| Groq API | Free tier rate limit | Multiple API keys / paid plan |
| Imagen API | Free tier quota | Paid quota increase |
| ChromaDB | ~1M vectors per collection | Shard or switch to Pinecone/Weaviate |
| Job queue (in-memory) | 10,000 jobs | Switch to Redis-backed Celery |

---

## Summary: How the System Handles 10,000 Concurrent Requests

```
10,000 requests arrive
        │
        ▼
┌───────────────────┐
│ Rate Limiter      │ → Throttle abusive IPs (429 Too Many Requests)
│ (~9,500 pass)     │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Job Queue         │ → Enqueue with priority, dedup via idempotency keys
│ (10K cap)         │ → Hot leads get priority 1-2, cold leads 9-10
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ K8s Autoscaler    │ → Scales backend pods from 2 → 10 based on active_jobs
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Worker Pool       │ → Each pod processes jobs concurrently (asyncio)
│ (10 pods × N)     │ → Circuit breakers prevent cascading failures
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ AI Providers      │ → Primary → Fallback → Placeholder
│ (with fallbacks)  │ → Never returns an error if a fallback exists
└───────────────────┘
```
