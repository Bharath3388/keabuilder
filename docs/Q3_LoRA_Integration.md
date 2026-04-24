# Q3: LoRA Model Integration for Personalised AI Images

## Design Overview

KeaBuilder integrates **LoRA (Low-Rank Adaptation)** models to generate brand-consistent, personalised images. Users upload a small set of reference images (e.g., their face, product shots, brand style), train a LoRA model, and then generate new images that preserve those visual features.

```
┌─────────────────────────────────────────────────────────┐
│                 LoRA Lifecycle                           │
│                                                         │
│  1. Upload Training Images                              │
│     POST /api/v1/lora/train                             │
│     ──────────────────────────                          │
│     ● MIME type validation (PNG, JPEG, WebP only)       │
│     ● Magic byte verification                           │
│     ● UUID-based filename sanitization                  │
│     ● Max 20 images per training job                    │
│                                                         │
│  2. Train LoRA Model                                    │
│     ──────────────────────                              │
│     Dev: Mock LoRA metadata created instantly            │
│     Prod: GPU training via Replicate / RunPod / Modal   │
│     ● Base model: SDXL (Stable Diffusion XL)            │
│     ● Default: 1500 training steps                      │
│     ● Trigger token: "ohwx person"                      │
│                                                         │
│  3. Generate With LoRA                                  │
│     POST /api/v1/lora/generate                          │
│     ──────────────────────────                          │
│     Dev: HuggingFace Inference API (no real LoRA)       │
│     Prod: Load .safetensors weights onto base SDXL      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Implementation:** `backend/services/lora_service.py`, `backend/api/routes/lora.py`

---

## How LoRA Integrates Into the Inference Pipeline

### Training Phase

```
User uploads 5-20 images
        │
        ▼
┌───────────────────┐
│  Validate Files   │  ● Check MIME type against ALLOWED_IMAGE_TYPES
│                   │  ● Verify magic bytes (PNG: \x89PNG, JPEG: \xFF\xD8\xFF)
│                   │  ● Rename to UUID (prevent path traversal)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Start Training   │
│                   │
│  Dev mode:        │  Create mock metadata JSON → status: "ready" immediately
│  Prod mode:       │  Dispatch to GPU provider (Replicate / RunPod / Modal)
│                   │  ● 10-15 minutes on A100 GPU
│                   │  ● Cost: ~$0.30-$0.80 per training
│                   │  ● Output: .safetensors weights file
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Store Metadata   │  loras/{user_id}/{lora_id}.json
│                   │
│  {                │
│    lora_id,       │
│    user_id,       │
│    trigger_token, │
│    training_steps,│
│    base_model,    │
│    status,        │
│    created_at     │
│  }                │
└───────────────────┘
```

### Inference Phase

```
User prompt: "Professional headshot in a modern office"
        │
        ▼
┌───────────────────┐
│  Load LoRA Meta   │  Read loras/{user_id}/{lora_id}.json
│                   │  Verify status == "ready"
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Inject Trigger   │  "ohwx person, Professional headshot in a modern office"
│  Token            │  (prepend the learned concept token)
└───────┬───────────┘
        │
        ├──── Dev Mode ──────────────────────┐
        │                                     ▼
        │                            ┌────────────────┐
        │                            │ HF Inference   │  Uses enhanced prompt
        │                            │ API (SDXL)     │  (no real LoRA weights)
        │                            └───────┬────────┘
        │                                    │ fallback
        │                            ┌────────────────┐
        │                            │ Pillow         │  Placeholder image
        │                            │ Placeholder    │
        │                            └───────┬────────┘
        │                                    │
        ├──── Prod Mode ─────────────────────┤
        │                                     │
        ▼                                     │
┌───────────────────┐                         │
│  Load Base SDXL   │                         │
│  + LoRA Weights   │  .safetensors file      │
│  (diffusers)      │                         │
└───────┬───────────┘                         │
        │                                     │
        ▼                                     │
┌───────────────────┐                         │
│  Run Inference    │                         │
│  steps=30         │                         │
│  guidance=7.5     │                         │
└───────┬───────────┘                         │
        │                                     │
        ▼                                     ▼
┌─────────────────────────────────────────────────┐
│  Upload to storage → Return asset_id + URL      │
└─────────────────────────────────────────────────┘
```

### Production GPU Inference (Planned)

In production, the inference uses the `diffusers` library:

```python
# Pseudocode for production inference
pipe = StableDiffusionXLPipeline.from_pretrained(base_model)
pipe.load_lora_weights(lora_path)  # .safetensors
pipe.fuse_lora(lora_scale=0.8)

image = pipe(
    prompt=full_prompt,
    num_inference_steps=30,
    guidance_scale=7.5,
).images[0]
```

---

## API Endpoints

### Start Training

```
POST /api/v1/lora/train
Content-Type: multipart/form-data
X-API-Key: <key>

Fields:
  user_id: string
  workspace_id: string
  lora_name: string
  trigger_token: string (default: "ohwx person")
  training_steps: int (default: 1500)
  images: File[] (5-20 images)
```

**Response:**
```json
{
  "job_id": "job_a1b2c3d4",
  "lora_id": "lora_e828b143",
  "status": "ready",
  "estimated_time_minutes": 0,
  "message": "Development mode: LoRA mock created instantly."
}
```

### Generate With LoRA

```
POST /api/v1/lora/generate
X-API-Key: <key>

{
  "user_id": "user_123",
  "workspace_id": "demo_workspace",
  "lora_id": "lora_e828b143",
  "prompt": "Professional headshot in a modern office",
  "num_inference_steps": 30,
  "guidance_scale": 7.5
}
```

**Response:**
```json
{
  "asset_id": "ast_20260424_lora_img_f2a3",
  "url": "/storage/demo_workspace/lora_images/ast_20260424_lora_img_f2a3.png",
  "lora_id": "lora_e828b143",
  "trigger_token": "ohwx person",
  "prompt_used": "ohwx person, Professional headshot in a modern office",
  "provider": "lora_inference"
}
```

### List User LoRAs

```
GET /api/v1/lora/list?user_id=user_123
X-API-Key: <key>
```

### Get Training Status

```
GET /api/v1/lora/status/{lora_id}?user_id=user_123
X-API-Key: <key>
```

---

## Security Measures

| Layer | Protection |
|-------|-----------|
| **Upload validation** | Only `image/png`, `image/jpeg`, `image/webp` MIME types accepted |
| **Magic byte check** | First bytes verified against known signatures to prevent disguised files |
| **Filename sanitization** | Original filenames discarded; replaced with `{uuid}.png` |
| **Auth** | All endpoints require `X-API-Key` header |
| **Path isolation** | Each user's LoRAs stored under `loras/{user_id}/` with path traversal prevention |
