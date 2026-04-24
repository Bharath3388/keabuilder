"""Q4: Similarity search API routes."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from models.schemas import (
    SimilaritySearchRequest,
    SimilaritySearchResponse,
    SimilarityResult,
)
from services.similarity_search import search_similar, index_asset
from api.middleware.auth import require_api_key

logger = structlog.get_logger()
router = APIRouter()


@router.post("/similar", response_model=SimilaritySearchResponse)
async def find_similar(req: SimilaritySearchRequest, _key: str = Depends(require_api_key)):
    """Find similar assets by text query."""
    try:
        results = await search_similar(
            query=req.query,
            workspace_id=req.workspace_id,
            embed_type=req.embed_type.value,
            top_k=req.top_k,
        )

        return SimilaritySearchResponse(
            results=[SimilarityResult(**r) for r in results["results"]],
            query_time_ms=results["query_time_ms"],
            total_results=results["total_results"],
        )
    except Exception as e:
        logger.error("search_failed", error=str(e))
        raise HTTPException(500, "Search failed. Please try again later.")


@router.post("/similar/image")
async def find_similar_by_image(
    workspace_id: str = Form(...),
    embed_type: str = Form("clip"),
    top_k: int = Form(10),
    image: UploadFile = File(...),
    _key: str = Depends(require_api_key),
):
    """Find similar assets by uploading an image (Gemini Vision or CLIP similarity)."""
    image_data = await image.read()
    if len(image_data) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image exceeds 10MB limit")

    try:
        results = await search_similar(
            query=image_data,
            workspace_id=workspace_id,
            embed_type=embed_type,
            top_k=top_k,
        )

        return SimilaritySearchResponse(
            results=[SimilarityResult(**r) for r in results["results"]],
            query_time_ms=results["query_time_ms"],
            total_results=results["total_results"],
        )
    except Exception as e:
        logger.error("image_search_failed", error=str(e))
        raise HTTPException(500, "Image search failed. Please try again later.")


@router.post("/index")
async def index_new_asset(
    asset_id: str = Form(...),
    workspace_id: str = Form(...),
    embed_type: str = Form("text"),
    text: str = Form(None),
    image: UploadFile = File(None),
    _key: str = Depends(require_api_key),
):
    """Manually index an asset for similarity search."""
    if embed_type == "text":
        if not text:
            raise HTTPException(400, "Text is required for text embedding")
        data = text
    elif embed_type in ("clip", "face"):
        if not image:
            raise HTTPException(400, "Image is required for image/face embedding")
        data = await image.read()
    else:
        raise HTTPException(400, f"Unknown embed type: {embed_type}")

    await index_asset(
        asset_id=asset_id,
        workspace_id=workspace_id,
        embed_type=embed_type,
        data=data,
        metadata={"asset_id": asset_id, "workspace_id": workspace_id},
    )

    return {"status": "indexed", "asset_id": asset_id, "embed_type": embed_type}
