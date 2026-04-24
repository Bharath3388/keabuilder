# Q5: Resilience, Fallback, and Degraded Mode

## Design Overview

Every external AI call in KeaBuilder is wrapped with a **three-layer resilience stack**: circuit breaker → retry with exponential backoff → fallback provider. This ensures the system never fails completely even when upstream APIs are down.

```
┌─────────────────────────────────────────────────────────┐
│                Resilience Stack                          │
│                                                         │
│  Layer 1: Circuit Breaker                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Per-service state machine: CLOSED → OPEN → HALF │    │
│  │ ● 5 consecutive failures → OPEN (skip primary)  │    │
│  │ ● 30 second cooldown → HALF-OPEN (test once)    │    │
│  │ ● 1 success in HALF-OPEN → CLOSED (resume)      │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Layer 2: Retry with Exponential Backoff                │
│  ┌─────────────────────────────────────────────────┐    │
│  │ ● Up to 3 attempts                              │    │
│  │ ● Backoff: 1s → 2s → 4s (max 10s)              │    │
│  │ ● Only retries: ConnectionError, TimeoutError,  │    │
│  │   OSError (not 4xx client errors)               │    │
│  │ ● Uses tenacity library                         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Layer 3: Fallback Provider                             │
│  ┌─────────────────────────────────────────────────┐    │
│  │ ● Each media type has a defined fallback chain   │    │
│  │ ● Fallback runs with its own timeout             │    │
│  │ ● If fallback also fails → raise to caller       │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Implementation:** `backend/services/resilience.py`, `backend/services/provider_graph.py`

---

## What Happens When a Model Fails

### The `call_with_fallback()` Flow

This is the primary entry point for all resilience-wrapped AI calls:

```
call_with_fallback(primary, fallback, service_name, timeout=15s)
        │
        ▼
┌───────────────────┐
│  Check Circuit    │
│  Breaker State    │
└───────┬───────────┘
        │
   ┌────┴────┐
   │         │
  CLOSED   OPEN ──▶ Skip primary entirely
   │                       │
   ▼                       │
┌───────────────────┐      │
│  Execute Primary  │      │
│  with Timeout     │      │
│  (15 seconds)     │      │
└───────┬───────────┘      │
        │                  │
   ┌────┴────┐             │
   │         │             │
 SUCCESS   FAILURE         │
   │         │             │
   ▼         ▼             │
 Record    Record          │
 Success   Failure         │
   │     (increment        │
   │      counter)         │
   │         │             │
   │         ▼             ▼
   │   ┌───────────────────────┐
   │   │  Execute Fallback     │
   │   │  with Timeout         │
   │   └───────┬───────────────┘
   │           │
   │      ┌────┴────┐
   │      │         │
   │    SUCCESS   FAILURE
   │      │         │
   │      │         ▼
   │      │    Log error + raise
   │      │    (Prometheus FALLBACK_COUNT incremented)
   │      │
   ▼      ▼
 Return result
```

### Circuit Breaker States

```
         success
    ┌────────────────┐
    │                │
    ▼                │
┌────────┐   5 fails   ┌────────┐   30s cooldown   ┌───────────┐
│ CLOSED │─────────────▶│  OPEN  │─────────────────▶│ HALF-OPEN │
│        │              │        │                  │           │
│ Normal │              │ Skip   │                  │ Test one  │
│ traffic│              │ primary│                  │ request   │
└────────┘              └────────┘                  └─────┬─────┘
    ▲                                                     │
    │                   success                           │
    └─────────────────────────────────────────────────────┘
                         │
                     failure → back to OPEN
```

Each service has its own independent circuit breaker:

```python
_breakers = {
    "imagen": SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
    "gemini": SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
    "groq":   SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
    "hf":     SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
}
```

---

## What Happens When an API Times Out

All external calls are wrapped with `asyncio.wait_for(func(), timeout)`:

1. **Timeout = 15 seconds** (default for all providers)
2. If the call exceeds the timeout, an `asyncio.TimeoutError` is raised
3. The circuit breaker records the failure
4. The fallback provider is attempted with its own timeout

---

## Fallback Chains by Media Type

### Image Generation

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Google Imagen    │  fail   │ HuggingFace     │  fail   │ Pillow          │
│ 4.0             │────────▶│ SDXL (free API) │────────▶│ Placeholder     │
│                 │         │                 │         │ (always works)  │
│ Best quality    │         │ Good quality    │         │ Text-on-image   │
│ ~2-5s latency   │         │ ~5-10s latency  │         │ ~0.01s latency  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

### Voice Generation

```
┌─────────────────┐         ┌─────────────────┐
│ Groq LLM        │  fail   │ Raw Prompt      │
│ Script Writer   │────────▶│ (use as-is)     │
└────────┬────────┘         └────────┬────────┘
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────┐
│ edge-tts (Microsoft free TTS)               │
│ Always available, runs locally              │
└─────────────────────────────────────────────┘
```

### Video Generation (Storyboard)

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Gemini 2.0      │  fail   │ Groq LLM        │  fail   │ Static          │
│ Flash           │────────▶│ (Llama 3.3)     │────────▶│ Template JSON   │
│                 │         │                 │         │ (always works)  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

### Lead Classification

```
┌─────────────────┐         ┌─────────────────┐
│ Groq LLM        │  fail   │ Rule-Based      │
│ (Llama 3.3)     │────────▶│ Weighted Scorer │
│                 │         │ (no API needed) │
│ Smart, nuanced  │         │ Deterministic   │
└─────────────────┘         └─────────────────┘
```

---

## Degraded Mode Behavior

When providers fail, the system degrades gracefully rather than returning errors:

| Scenario | Behavior | User Impact |
|----------|----------|-------------|
| Imagen API down | HF SDXL generates image | Slightly lower quality, slower |
| All image APIs down | Pillow placeholder generated | Image with prompt text overlay |
| Groq API down | Rule-based classifier used | Slightly less nuanced scoring |
| Gemini embedding down | Local sentence-transformers used | Lower-dim embeddings, still works |
| CLIP model fails | Error returned for image search only | Text search unaffected |
| Face model unavailable | Face search disabled, returns empty | Other search types work normally |
| Circuit breaker OPEN | Primary skipped for 30s | Faster response (no wasted timeout) |

---

## Monitoring & Observability

The resilience layer emits Prometheus metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `ai_call_total` | Counter | Total AI calls by provider and status |
| `ai_call_duration_seconds` | Histogram | Latency per provider |
| `fallback_total` | Counter | Number of fallback activations by service |
| `circuit_breaker_state` | Gauge | Current state of each circuit breaker |

These metrics are exposed at `GET /metrics` for Prometheus scraping and Grafana dashboards.

---

## Sample Failure Scenario

**Timeline of an Imagen outage:**

```
T+0s    Image request → Imagen call starts
T+15s   Imagen times out (asyncio.TimeoutError)
        → Circuit breaker records failure #1
        → Fallback to HuggingFace SDXL
T+20s   HF returns image successfully
        → Response returned to user (slightly delayed)

... 4 more Imagen failures in next few minutes ...

T+5min  Failure #5 recorded
        → Circuit breaker OPENS for "imagen"
        → All subsequent image requests skip Imagen entirely
        → Go directly to HF SDXL (faster response)

T+5.5min  30s cooldown expires
        → Circuit breaker enters HALF-OPEN
        → Next request tries Imagen once as a test

T+5.5min  Imagen responds successfully
        → Circuit breaker CLOSES
        → Normal routing resumes
```
