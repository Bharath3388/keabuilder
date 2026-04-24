"""Q2: LangGraph Multi-Provider Content Router.

Implements the problem statement requirement:
  - Images  → Imagen 4.0 (Google) primary, HuggingFace SDXL fallback
  - Voice   → edge-tts (free) with Groq LLM script generation
  - Video   → Gemini 2.0 Flash (storyboard + description)

Uses LangGraph to orchestrate the routing as a state machine,
and LangChain for provider integration.

Architecture:
  ┌─────────────┐
  │   classify   │  Determine media_type
  └──────┬───────┘
         │
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
 ┌──────┐ ┌───────┐ ┌───────┐
 │image │ │ voice │ │ video │
 │node  │ │ node  │ │ node  │
 └──┬───┘ └──┬────┘ └──┬────┘
    │         │         │
    ▼         ▼         ▼
 ┌─────────────────────────┐
 │     store_asset          │  Save to storage + DB
 └─────────────────────────┘
"""

import io
import asyncio
import structlog
from typing import TypedDict, Literal, Optional

from langgraph.graph import StateGraph, END

from config import get_settings
from utils.storage import get_storage, generate_asset_id
from utils.monitoring import AI_CALL_COUNT, Timer
from utils.sanitize import sanitize_prompt
from services.resilience import call_with_fallback

logger = structlog.get_logger()
settings = get_settings()


# =============================================================================
# LangGraph State Definition
# =============================================================================

class ContentState(TypedDict):
    """State flowing through the content generation graph."""
    media_type: str
    prompt: str
    workspace_id: str
    user_id: str
    width: int
    height: int
    voice_id: Optional[str]
    style: Optional[str]
    # Filled by provider nodes
    data: Optional[bytes]
    provider_used: Optional[str]
    ext: Optional[str]
    subfolder: Optional[str]
    script: Optional[str]
    # Filled by store node
    asset_id: Optional[str]
    url: Optional[str]
    error: Optional[str]


# =============================================================================
# Provider Nodes
# =============================================================================

async def image_node(state: ContentState) -> ContentState:
    """Image generation node: Imagen 4.0 (primary) → HuggingFace (fallback)."""
    prompt = sanitize_prompt(state["prompt"])
    width = state.get("width", 1024)
    height = state.get("height", 1024)

    async def _imagen_generate() -> bytes:
        """Primary: Google Imagen 4.0 via google-genai SDK."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        def _call():
            response = client.models.generate_images(
                model=settings.gemini_image_model,
                prompt=prompt,
                config=types.GenerateImagesConfig(number_of_images=1),
            )
            return response.generated_images[0].image.image_bytes

        data = await asyncio.to_thread(_call)
        AI_CALL_COUNT.labels(provider="imagen", type="image", status="success").inc()
        logger.info("image_generated", provider="imagen-4.0", size=len(data))
        return data

    async def _hf_generate() -> bytes:
        """Fallback: HuggingFace Inference API (SDXL)."""
        from huggingface_hub import InferenceClient

        def _call():
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

        data = await asyncio.to_thread(_call)
        AI_CALL_COUNT.labels(provider="huggingface", type="image", status="success").inc()
        logger.info("image_generated", provider="huggingface-sdxl", size=len(data))
        return data

    # Route: Imagen primary, HuggingFace fallback
    if settings.gemini_api_key:
        data = await call_with_fallback(
            primary=_imagen_generate,
            fallback=_hf_generate if settings.hf_api_token else None,
            service_name="image_generation",
        )
        provider = "imagen-4.0"
    elif settings.hf_api_token:
        data = await _hf_generate()
        provider = "huggingface"
    else:
        from services.content_router import generate_image_placeholder
        data = await generate_image_placeholder(prompt, width, height)
        provider = "placeholder"

    state["data"] = data
    state["provider_used"] = provider
    state["ext"] = "png"
    state["subfolder"] = "images"
    return state


async def voice_node(state: ContentState) -> ContentState:
    """Voice generation node: Gemini script generation + Gemini TTS, edge-tts fallback."""
    prompt = sanitize_prompt(state["prompt"])
    voice_id = state.get("voice_id")

    # Step 1: Generate professional voiceover script via Gemini (or Groq fallback)
    script = prompt
    if settings.gemini_api_key:
        try:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model=settings.gemini_text_model,
                contents=(
                    "You are a professional voiceover script writer. "
                    "Given a user's prompt or description, generate a polished, "
                    "natural-sounding voiceover script ready to be spoken aloud. "
                    "Keep it concise (2-4 sentences). Do NOT include stage directions, "
                    "speaker labels, or quotation marks. Output ONLY the script text.\n\n"
                    f"Prompt: {prompt}"
                ),
            )
            script = response.text.strip()
            logger.info("voice_script_generated", provider="gemini", length=len(script))
        except Exception as e:
            logger.warning("voice_script_gemini_failed", error=str(e))
            # Fallback to Groq for script
            if settings.groq_api_key:
                try:
                    from groq import AsyncGroq
                    groq_client = AsyncGroq(api_key=settings.groq_api_key)
                    resp = await groq_client.chat.completions.create(
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
                    script = resp.choices[0].message.content.strip()
                    logger.info("voice_script_generated", provider="groq", length=len(script))
                except Exception as e2:
                    logger.warning("voice_script_fallback", error=str(e2))

    # Step 2: Convert script to speech — Gemini TTS primary, edge-tts fallback
    data = None
    tts_provider = "edge-tts"

    if settings.gemini_api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=script,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_id or "Kore",
                            )
                        )
                    ),
                ),
            )
            audio_part = response.candidates[0].content.parts[0]
            # Gemini returns raw PCM — convert to WAV
            import wave
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(24000)
                wf.writeframes(audio_part.inline_data.data)
            data = audio_buffer.getvalue()
            tts_provider = "gemini-tts"
            logger.info("voice_generated", provider="gemini-tts", size=len(data))
        except Exception as e:
            logger.warning("gemini_tts_failed_trying_edge_tts", error=str(e))

    # Fallback: edge-tts
    if data is None:
        try:
            import edge_tts
            voice = voice_id or settings.tts_default_voice
            communicate = edge_tts.Communicate(script, voice)
            audio_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            data = audio_buffer.getvalue()
            tts_provider = "edge-tts"
            logger.info("voice_generated", provider="edge-tts", size=len(data))
        except Exception as e:
            logger.error("voice_generation_failed", error=str(e))
            raise

    AI_CALL_COUNT.labels(provider=tts_provider, type="voice", status="success").inc()

    state["data"] = data
    state["provider_used"] = tts_provider
    state["ext"] = "wav" if tts_provider == "gemini-tts" else "mp3"
    state["subfolder"] = "voice"
    state["script"] = script
    return state


async def video_node(state: ContentState) -> ContentState:
    """Video generation node: Gemini for storyboard + description.

    Since no free video generation API exists, we use Gemini to generate
    a professional video storyboard/script that could be used with
    Runway ML, Pika Labs, etc.
    """
    import json
    prompt = sanitize_prompt(state["prompt"])

    storyboard = None
    provider = "placeholder"

    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)

            def _call():
                return client.models.generate_content(
                    model=settings.gemini_text_model,
                    contents=(
                        f"Create a professional video storyboard for this concept: {prompt}\n\n"
                        "Return a JSON object with these fields:\n"
                        '- "title": short video title\n'
                        '- "duration_seconds": suggested duration (5-30)\n'
                        '- "scenes": array of objects, each with "scene_number", "description", '
                        '"duration_seconds", "camera_angle", "visual_style"\n'
                        '- "voiceover_script": narration text for the video\n'
                        '- "music_mood": suggested background music mood\n'
                        "Return ONLY valid JSON, no markdown."
                    ),
                )

            response = await asyncio.to_thread(_call)
            text = response.text.strip()
            # Clean markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            storyboard = json.loads(text)
            provider = "gemini-2.0-flash"
            AI_CALL_COUNT.labels(provider="gemini", type="video", status="success").inc()
            logger.info("video_storyboard_generated", provider="gemini")
        except Exception as e:
            logger.warning("gemini_storyboard_failed", error=str(e))

    if storyboard is None and settings.groq_api_key:
        # Fallback: use Groq LLM for storyboard generation
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.groq_api_key)
            storyboard_prompt = (
                f"Create a professional video storyboard for this concept: {prompt}\n\n"
                "Return a JSON object with these fields:\n"
                '- "title": short video title\n'
                '- "duration_seconds": suggested duration (5-30)\n'
                '- "scenes": array of objects, each with "scene_number", "description", '
                '"duration_seconds", "camera_angle", "visual_style"\n'
                '- "voiceover_script": narration text for the video\n'
                '- "music_mood": suggested background music mood\n'
                "Return ONLY valid JSON, no markdown."
            )
            response = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": storyboard_prompt}],
                temperature=0.7,
                max_tokens=1000,
            )
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            storyboard = json.loads(text)
            provider = "groq"
            logger.info("video_storyboard_generated", provider="groq")
        except Exception as e:
            logger.warning("groq_storyboard_failed", error=str(e))

    if storyboard is None:
        storyboard = {
            "title": f"Video: {prompt[:50]}",
            "status": "storyboard_placeholder",
            "prompt": prompt,
            "message": "Video generation requires a GPU provider (Runway ML, Pika Labs). "
                       "Storyboard generated as planning document.",
        }

    data = json.dumps(storyboard, indent=2).encode()
    state["data"] = data
    state["provider_used"] = provider
    state["ext"] = "json"
    state["subfolder"] = "video"
    return state


async def store_asset_node(state: ContentState) -> ContentState:
    """Store generated content to storage and return asset metadata."""
    storage = get_storage()
    asset_id = generate_asset_id(state["media_type"])
    filename = f"{asset_id}.{state['ext']}"
    url = await storage.upload(
        state["data"], state["workspace_id"], state["subfolder"], filename
    )
    state["asset_id"] = asset_id
    state["url"] = url
    return state


# =============================================================================
# LangGraph Router
# =============================================================================

def _route_by_media_type(state: ContentState) -> str:
    """Routing function: dispatch to the correct provider node."""
    media_type = state["media_type"]
    if media_type == "image":
        return "image_node"
    elif media_type == "voice":
        return "voice_node"
    elif media_type == "video":
        return "video_node"
    raise ValueError(f"Unsupported media type: {media_type}")


def build_content_graph() -> StateGraph:
    """Build the LangGraph state machine for content generation.

    Graph structure:
        classify → (image_node | voice_node | video_node) → store_asset → END
    """
    graph = StateGraph(ContentState)

    # Add nodes
    graph.add_node("image_node", image_node)
    graph.add_node("voice_node", voice_node)
    graph.add_node("video_node", video_node)
    graph.add_node("store_asset", store_asset_node)

    # Entry: route by media type
    graph.set_conditional_entry_point(_route_by_media_type)

    # All provider nodes flow to store_asset
    graph.add_edge("image_node", "store_asset")
    graph.add_edge("voice_node", "store_asset")
    graph.add_edge("video_node", "store_asset")

    # store_asset → END
    graph.add_edge("store_asset", END)

    return graph.compile()


# Module-level compiled graph (reusable)
_content_graph = None


def get_content_graph():
    """Get or build the compiled content generation graph."""
    global _content_graph
    if _content_graph is None:
        _content_graph = build_content_graph()
        logger.info("LangGraph content router initialized")
    return _content_graph


# =============================================================================
# Public API
# =============================================================================

async def route_generation_langgraph(
    media_type: str,
    prompt: str,
    workspace_id: str,
    user_id: str,
    width: int = 1024,
    height: int = 1024,
    voice_id: str | None = None,
    style: str | None = None,
) -> dict:
    """Route content generation through the LangGraph state machine."""
    graph = get_content_graph()

    initial_state: ContentState = {
        "media_type": media_type,
        "prompt": prompt,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "width": width,
        "height": height,
        "voice_id": voice_id,
        "style": style,
        "data": None,
        "provider_used": None,
        "ext": None,
        "subfolder": None,
        "script": None,
        "asset_id": None,
        "url": None,
        "error": None,
    }

    # Execute the graph
    result = await graph.ainvoke(initial_state)

    return {
        "asset_id": result["asset_id"],
        "status": "completed",
        "url": result["url"],
        "provider_used": result["provider_used"],
        "type": media_type,
        "size_bytes": len(result["data"]) if result["data"] else 0,
        "width": width if media_type == "image" else None,
        "height": height if media_type == "image" else None,
        "script": result.get("script"),
    }
