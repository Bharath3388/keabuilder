"""Q2 + Q5: Multi-Modal Content Generation Router with Resilience.

Provider-agnostic routing layer. Uses free/open-source providers:
- Image: Hugging Face Inference API (free tier)
- Voice: edge-tts (free Microsoft TTS)
- Video: Placeholder (no free high-quality API available)

Includes circuit breaker + fallback logic (Q5).
"""

import io
import uuid
import hashlib
import structlog
from datetime import datetime

from config import get_settings
from utils.storage import get_storage, generate_asset_id
from utils.monitoring import AI_CALL_COUNT, AI_CALL_LATENCY, Timer
from services.resilience import call_with_fallback

logger = structlog.get_logger()
settings = get_settings()


# =============================================================================
# Image Generation — Hugging Face Inference API (FREE)
# =============================================================================

async def generate_image_hf(prompt: str, width: int = 1024, height: int = 1024) -> bytes:
    """Generate image using Hugging Face Inference API (free tier) via SDK."""
    import asyncio
    from huggingface_hub import InferenceClient

    def _generate():
        client = InferenceClient(token=settings.hf_api_token)
        image = client.text_to_image(
            prompt,
            model=settings.hf_image_model,
            width=min(width, 1024),
            height=min(height, 1024),
        )
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    with Timer("image_generation", {"provider": "huggingface"}):
        data = await asyncio.to_thread(_generate)

    AI_CALL_COUNT.labels(provider="huggingface", type="image", status="success").inc()
    return data


async def generate_image_placeholder(prompt: str, width: int = 1024, height: int = 1024) -> bytes:
    """Generate a placeholder image (fallback when no API is available)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(45, 55, 72))
    draw = ImageDraw.Draw(img)

    # Draw prompt text
    text = f"[AI Image]\n{prompt[:80]}..."
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((width // 8, height // 3), text, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# =============================================================================
# Voice/TTS Generation — edge-tts (FREE)
# =============================================================================

async def generate_voice_script(prompt: str) -> str:
    """Use Groq LLM to generate a professional voiceover script from a prompt."""
    if not settings.groq_api_key:
        return prompt  # Fallback: use raw prompt if no LLM

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional voiceover script writer. "
                        "Given a user's prompt or description, generate a polished, "
                        "natural-sounding voiceover script ready to be spoken aloud. "
                        "Keep it concise (2-4 sentences). Do NOT include stage directions, "
                        "speaker labels, or quotation marks. Output ONLY the script text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        script = response.choices[0].message.content.strip()
        logger.info("voice_script_generated", prompt=prompt[:50], script_length=len(script))
        return script
    except Exception as e:
        logger.warning("voice_script_generation_failed", error=str(e))
        return prompt  # Fallback: use raw prompt


async def generate_voice_edge_tts(text: str, voice: str | None = None) -> bytes:
    """Generate speech using edge-tts (free Microsoft TTS)."""
    import edge_tts

    voice = voice or settings.tts_default_voice
    communicate = edge_tts.Communicate(text, voice)

    audio_buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.write(chunk["data"])

    AI_CALL_COUNT.labels(provider="edge-tts", type="voice", status="success").inc()
    return audio_buffer.getvalue()


# =============================================================================
# Video Generation — Placeholder (no free API available)
# =============================================================================

async def generate_video_placeholder(prompt: str) -> bytes:
    """Placeholder for video generation.
    In production, this would call Runway ML, Pika Labs, or Kling AI.
    """
    # Create a simple placeholder response
    placeholder_data = {
        "status": "video_generation_requires_gpu",
        "prompt": prompt,
        "message": "Video generation requires a GPU provider (Runway ML, Pika Labs). "
                   "Configure RUNWAY_API_KEY in .env to enable.",
    }
    import json
    return json.dumps(placeholder_data).encode()


# =============================================================================
# Content Router
# =============================================================================

async def route_generation(
    media_type: str,
    prompt: str,
    workspace_id: str,
    user_id: str,
    width: int = 1024,
    height: int = 1024,
    voice_id: str | None = None,
    style: str | None = None,
) -> dict:
    """Route content generation to the appropriate provider."""
    storage = get_storage()
    asset_id = generate_asset_id(media_type)
    provider_used = "unknown"

    if media_type == "image":
        # Try HF API, fallback to placeholder
        if settings.hf_api_token:
            data = await call_with_fallback(
                primary=lambda: generate_image_hf(prompt, width, height),
                fallback=lambda: generate_image_placeholder(prompt, width, height),
                service_name="image_generation",
            )
            provider_used = "huggingface" if settings.hf_api_token else "placeholder"
        else:
            data = await generate_image_placeholder(prompt, width, height)
            provider_used = "placeholder"

        ext = "png"
        filename = f"{asset_id}.{ext}"
        url = await storage.upload(data, workspace_id, "images", filename)

    elif media_type == "voice":
        # Step 1: Generate a professional voiceover script from the prompt
        script = await generate_voice_script(prompt)
        # Step 2: Convert script to speech
        data = await call_with_fallback(
            primary=lambda: generate_voice_edge_tts(script, voice_id),
            fallback=lambda: generate_voice_edge_tts(script),  # Default voice
            service_name="voice_generation",
        )
        provider_used = "edge-tts"
        ext = "mp3"
        filename = f"{asset_id}.{ext}"
        url = await storage.upload(data, workspace_id, "voice", filename)

    elif media_type == "video":
        data = await generate_video_placeholder(prompt)
        provider_used = "placeholder"
        ext = "json"
        filename = f"{asset_id}.{ext}"
        url = await storage.upload(data, workspace_id, "video", filename)

    else:
        raise ValueError(f"Unsupported media type: {media_type}")

    result = {
        "asset_id": asset_id,
        "status": "completed",
        "url": url,
        "provider_used": provider_used,
        "type": media_type,
        "size_bytes": len(data),
        "width": width if media_type == "image" else None,
        "height": height if media_type == "image" else None,
    }

    # Include generated script for voice content
    if media_type == "voice":
        result["script"] = script

    return result
