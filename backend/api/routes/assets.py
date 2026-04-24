"""Asset management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from models.database import get_db, AssetRecord
from services.queue_service import get_job_status, get_queue_stats, enqueue_job
from api.middleware.auth import require_api_key

router = APIRouter()


@router.get("")
@router.get("/")
async def list_assets(
    workspace_id: str = Query(...),
    type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """List assets for a workspace with pagination."""
    query = db.query(AssetRecord).filter(AssetRecord.workspace_id == workspace_id)

    if type:
        query = query.filter(AssetRecord.type == type)

    total = query.count()
    assets = (
        query.order_by(AssetRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "assets": [
            {
                "asset_id": a.id,
                "type": a.type,
                "url": a.url,
                "thumbnail_url": a.thumbnail_url,
                "prompt": a.prompt,
                "provider": a.provider,
                "tags": a.tags or [],
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in assets
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/job/{job_id}")
async def check_job_status(job_id: str, _key: str = Depends(require_api_key)):
    """Check the status of an async generation job."""
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/queue/stats")
async def queue_statistics(_key: str = Depends(require_api_key)):
    """Get queue statistics (admin endpoint)."""
    return get_queue_stats()


@router.post("/job/enqueue")
async def enqueue_generation_job(
    job_type: str,
    user_id: str,
    workspace_id: str,
    prompt: str,
    priority: int = 5,
    _key: str = Depends(require_api_key),
):
    """Enqueue an async generation job."""
    job = await enqueue_job(
        job_type=job_type,
        user_id=user_id,
        workspace_id=workspace_id,
        input_data={"prompt": prompt},
        priority=priority,
    )
    return {"job_id": job["job_id"], "status": job["status"]}
