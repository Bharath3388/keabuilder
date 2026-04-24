"""Q2: Content generation API routes — powered by LangGraph multi-provider router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.schemas import GenerateRequest, GenerateResponse, AssetMetadata, Dimensions
from models.database import get_db, AssetRecord
from services.provider_graph import route_generation_langgraph
from services.similarity_search import index_asset
from config import get_settings
from utils.storage import hash_prompt
from api.middleware.auth import require_api_key
from datetime import datetime
import structlog

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate_content(req: GenerateRequest, db: Session = Depends(get_db), _key: str = Depends(require_api_key)):
    """Generate image, video, or voice content via the LangGraph multi-provider router.

    Routing:
      - Image  → Imagen 4.0 (Google) primary, HuggingFace SDXL fallback
      - Voice  → Groq LLM script + edge-tts synthesis
      - Video  → Gemini 2.0 Flash storyboard generation
    """
    width = req.dimensions.width if req.dimensions else 1024
    height = req.dimensions.height if req.dimensions else 1024

    try:
        result = await route_generation_langgraph(
            media_type=req.type.value,
            prompt=req.prompt,
            workspace_id=req.workspace_id,
            user_id=req.user_id,
            width=width,
            height=height,
            voice_id=req.voice_id,
            style=req.style,
        )
    except Exception as e:
        logger.error("generation_failed", type=req.type.value, error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Content generation failed: {type(e).__name__}. Please try again.",
        )

    # Persist asset record
    asset_record = AssetRecord(
        id=result["asset_id"],
        workspace_id=req.workspace_id,
        user_id=req.user_id,
        type=req.type.value,
        url=result["url"],
        prompt=req.prompt,
        prompt_hash=hash_prompt(req.prompt),
        provider=result["provider_used"],
        style=req.style,
        width=result.get("width"),
        height=result.get("height"),
        size_bytes=result.get("size_bytes", 0),
        tags=[],
    )
    db.add(asset_record)
    db.commit()

    # Auto-index asset for similarity search
    try:
        asset_metadata = {
            "asset_id": result["asset_id"],
            "workspace_id": req.workspace_id,
            "type": req.type.value,
            "prompt": req.prompt,
            "url": result["url"],
            "provider": result["provider_used"],
        }

        # Index text embedding for all asset types
        index_text = f"{req.prompt} {req.style or ''} {req.type.value}"
        await index_asset(
            asset_id=result["asset_id"],
            workspace_id=req.workspace_id,
            embed_type="text",
            data=index_text.strip(),
            metadata=asset_metadata,
        )

        # Also index image assets with clip embedding for image-to-image search
        if req.type.value == "image" and result.get("size_bytes", 0) > 0:
            import os
            image_path = os.path.join(
                settings.storage_local_path,
                req.workspace_id, "images",
                f"{result['asset_id']}.png"
            )
            if os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_data = f.read()
                await index_asset(
                    asset_id=result["asset_id"],
                    workspace_id=req.workspace_id,
                    embed_type="clip",
                    data=image_data,
                    metadata=asset_metadata,
                )
                logger.info("image_clip_indexed", asset_id=result["asset_id"])

        logger.info("asset_auto_indexed", asset_id=result["asset_id"])
    except Exception as e:
        logger.warning("asset_index_failed", error=str(e))

    metadata = AssetMetadata(
        type=req.type,
        dimensions=Dimensions(width=width, height=height) if req.type.value == "image" else None,
        size_bytes=result.get("size_bytes", 0),
    )

    return GenerateResponse(
        asset_id=result["asset_id"],
        status=result["status"],
        url=result["url"],
        provider_used=result["provider_used"],
        metadata=metadata,
        script=result.get("script"),
    )
