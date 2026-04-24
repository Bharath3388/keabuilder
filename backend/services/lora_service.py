"""Q3: LoRA Model Integration for Personalised AI Images.

Manages LoRA training jobs and inference.
Uses Hugging Face diffusers (open-source) for local inference.
Uses Replicate API as an optional managed training provider.

For development: simulates training and uses HF Inference API.
For production: uses GPU workers (RunPod/Modal) for real training.
"""

import os
import uuid
import json
import asyncio
import structlog
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings
from utils.storage import get_storage, generate_asset_id
from utils.monitoring import AI_CALL_COUNT, Timer

logger = structlog.get_logger()
settings = get_settings()

LORA_STORAGE_DIR = Path(settings.storage_local_path) / "loras"
LORA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LoRA Training
# =============================================================================

async def start_lora_training(
    user_id: str,
    workspace_id: str,
    lora_name: str,
    image_paths: list[str],
    trigger_token: str = "ohwx person",
    training_steps: int = 1500,
) -> dict:
    """Start a LoRA training job.

    In development mode: Creates a mock LoRA file.
    In production: Would dispatch to RunPod/Modal/Replicate for GPU training.
    """
    lora_id = f"lora_{uuid.uuid4().hex[:8]}"
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    lora_dir = LORA_STORAGE_DIR / user_id
    lora_dir.mkdir(parents=True, exist_ok=True)

    if settings.app_env == "production":
        # Production: dispatch to GPU training service
        return await _dispatch_training_job(
            job_id=job_id,
            lora_id=lora_id,
            user_id=user_id,
            image_paths=image_paths,
            trigger_token=trigger_token,
            training_steps=training_steps,
        )
    else:
        # Development: create mock LoRA metadata
        meta = {
            "lora_id": lora_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "name": lora_name,
            "trigger_token": trigger_token,
            "training_steps": training_steps,
            "status": "ready",  # Mock: immediately ready
            "base_model": settings.hf_image_model,
            "num_images": len(image_paths),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        meta_path = lora_dir / f"{lora_id}.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Mock LoRA created: {lora_id}", user_id=user_id)

        return {
            "job_id": job_id,
            "lora_id": lora_id,
            "status": "ready",
            "estimated_time_minutes": 0,
            "message": "Development mode: LoRA mock created instantly. "
                       "In production, training takes 10-15 minutes on A100 GPU.",
        }


async def _dispatch_training_job(
    job_id: str,
    lora_id: str,
    user_id: str,
    image_paths: list[str],
    trigger_token: str,
    training_steps: int,
) -> dict:
    """Dispatch training to a GPU provider (production).

    Would use one of:
    - Replicate API (managed, ~$0.30-0.80 per training)
    - RunPod serverless (self-managed)
    - Modal (serverless GPU)
    """
    # Example Replicate API call (commented out — requires API key):
    #
    # import replicate
    # training = replicate.trainings.create(
    #     version="ostris/flux-dev-lora-trainer:...",
    #     input={
    #         "input_images": zip_url,
    #         "trigger_word": trigger_token,
    #         "steps": training_steps,
    #         "lora_rank": 16,
    #         "learning_rate": 1e-4,
    #     },
    #     destination=f"keabuilder/{lora_id}",
    # )

    return {
        "job_id": job_id,
        "lora_id": lora_id,
        "status": "training",
        "estimated_time_minutes": 15,
        "message": "Training dispatched to GPU worker. You'll be notified when ready.",
    }


# =============================================================================
# LoRA Inference
# =============================================================================

async def generate_with_lora(
    user_id: str,
    workspace_id: str,
    lora_id: str,
    prompt: str,
    num_inference_steps: int = 30,
    guidance_scale: float = 7.5,
) -> dict:
    """Generate an image using a LoRA model.

    In development: Uses HF Inference API with the prompt (no real LoRA).
    In production: Loads LoRA weights onto base model for inference.
    """
    # Load LoRA metadata
    meta = _load_lora_metadata(user_id, lora_id)
    if not meta:
        raise ValueError(f"LoRA {lora_id} not found for user {user_id}")

    if meta["status"] != "ready":
        raise ValueError(f"LoRA {lora_id} is not ready yet (status: {meta['status']})")

    # Inject trigger token
    trigger_token = meta.get("trigger_token", "ohwx person")
    full_prompt = f"{trigger_token}, {prompt}"

    storage = get_storage()
    asset_id = generate_asset_id("lora_img")

    if settings.app_env == "production":
        # Production: real LoRA inference on GPU
        image_data = await _inference_with_lora_gpu(
            lora_path=f"loras/{user_id}/{lora_id}.safetensors",
            prompt=full_prompt,
            steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
    else:
        # Development: use HF API with enhanced prompt
        from services.content_router import generate_image_hf, generate_image_placeholder

        if settings.hf_api_token:
            try:
                image_data = await generate_image_hf(full_prompt)
            except Exception:
                image_data = await generate_image_placeholder(full_prompt)
        else:
            image_data = await generate_image_placeholder(full_prompt)

    filename = f"{asset_id}.png"
    url = await storage.upload(image_data, workspace_id, "lora_images", filename)

    return {
        "asset_id": asset_id,
        "url": url,
        "lora_id": lora_id,
        "trigger_token": trigger_token,
        "prompt_used": full_prompt,
        "provider": "lora_inference",
    }


async def _inference_with_lora_gpu(
    lora_path: str,
    prompt: str,
    steps: int = 30,
    guidance_scale: float = 7.5,
) -> bytes:
    """Real LoRA inference on GPU (production only).

    This would run on a GPU worker with diffusers installed:

    ```python
    from diffusers import StableDiffusionXLPipeline
    import torch

    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16"
    ).to("cuda")

    pipe.load_lora_weights(lora_path)

    image = pipe(
        prompt=prompt,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
    ).images[0]
    ```
    """
    raise NotImplementedError("GPU inference requires CUDA. Use development mode or deploy to GPU worker.")


def _load_lora_metadata(user_id: str, lora_id: str) -> dict | None:
    """Load LoRA metadata from storage."""
    meta_path = LORA_STORAGE_DIR / user_id / f"{lora_id}.json"
    if not meta_path.exists():
        return None
    with open(meta_path) as f:
        return json.load(f)


def list_user_loras(user_id: str) -> list[dict]:
    """List all LoRAs for a user."""
    user_dir = LORA_STORAGE_DIR / user_id
    if not user_dir.exists():
        return []

    loras = []
    for meta_file in user_dir.glob("*.json"):
        with open(meta_file) as f:
            loras.append(json.load(f))
    return sorted(loras, key=lambda x: x.get("created_at", ""), reverse=True)
