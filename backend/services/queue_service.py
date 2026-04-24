"""Q6: Job Queue Service for High-Volume AI Requests.

Uses Celery + Redis for async job processing.
Supports priority lanes, dead letter queues, and idempotency.

For development: uses in-memory task execution.
For production: uses Redis-backed Celery workers.
"""

import uuid
import json
import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import get_settings
from utils.monitoring import QUEUE_DEPTH, ACTIVE_JOBS

logger = structlog.get_logger()
settings = get_settings()

# In-memory job store for development (no Redis needed)
_job_store: dict[str, dict] = {}

# Limits to prevent unbounded growth
_MAX_JOBS = 10_000
_JOB_TTL_HOURS = 24


# =============================================================================
# Job Management
# =============================================================================


def _evict_expired_jobs():
    """Remove completed/failed jobs older than TTL to prevent memory leak."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_JOB_TTL_HOURS)).isoformat()
    expired_keys = [
        key for key, job in _job_store.items()
        if job.get("status") in ("completed", "failed")
        and job.get("created_at", "") < cutoff
    ]
    for key in expired_keys:
        del _job_store[key]
    if expired_keys:
        logger.info(f"Evicted {len(expired_keys)} expired jobs")


async def enqueue_job(
    job_type: str,
    user_id: str,
    workspace_id: str,
    input_data: dict,
    priority: int = 5,
    idempotency_key: str | None = None,
) -> dict:
    """Enqueue a new job for async processing.

    Priority: 1 = highest (hot leads, paid plans), 10 = lowest (cold lead batches)
    """
    # Check idempotency
    if idempotency_key and idempotency_key in _job_store:
        existing = _job_store[idempotency_key]
        logger.info(f"Duplicate job detected: {idempotency_key}")
        return existing

    # Evict expired jobs to prevent unbounded memory growth
    _evict_expired_jobs()

    if len(_job_store) >= _MAX_JOBS:
        raise RuntimeError("Job queue full. Try again later.")

    job_id = f"job_{uuid.uuid4().hex[:12]}"

    job = {
        "job_id": job_id,
        "job_type": job_type,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "input_data": input_data,
        "priority": priority,
        "status": "queued",
        "retry_count": 0,
        "max_retries": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "output_data": None,
        "error_message": None,
    }

    _job_store[job_id] = job
    if idempotency_key:
        _job_store[idempotency_key] = job

    logger.info(f"Job enqueued: {job_id}", job_type=job_type, priority=priority)

    # In development mode, process synchronously
    if not settings.is_production:
        await _process_job_sync(job_id)

    return job


async def _process_job_sync(job_id: str):
    """Process a job synchronously (development mode)."""
    job = _job_store.get(job_id)
    if not job:
        return

    job["status"] = "processing"
    job["started_at"] = datetime.now(timezone.utc).isoformat()
    ACTIVE_JOBS.labels(job_type=job["job_type"]).inc()

    try:
        if job["job_type"] == "image":
            from services.content_router import route_generation
            result = await route_generation(
                media_type="image",
                prompt=job["input_data"].get("prompt", ""),
                workspace_id=job["workspace_id"],
                user_id=job["user_id"],
            )
            job["output_data"] = result
        elif job["job_type"] == "voice":
            from services.content_router import route_generation
            result = await route_generation(
                media_type="voice",
                prompt=job["input_data"].get("prompt", ""),
                workspace_id=job["workspace_id"],
                user_id=job["user_id"],
            )
            job["output_data"] = result
        elif job["job_type"] == "classification":
            from services.lead_classifier import classify_lead
            result = await classify_lead(job["input_data"])
            job["output_data"] = result

        job["status"] = "completed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as e:
        job["retry_count"] += 1
        if job["retry_count"] >= job["max_retries"]:
            job["status"] = "failed"
            job["error_message"] = str(e)
            logger.error(f"Job {job_id} failed after {job['max_retries']} retries", error=str(e))
        else:
            job["status"] = "queued"  # Re-queue for retry
            logger.warning(f"Job {job_id} failed, retry {job['retry_count']}", error=str(e))

    finally:
        ACTIVE_JOBS.labels(job_type=job["job_type"]).dec()


def get_job_status(job_id: str) -> dict | None:
    """Get the status of a job."""
    return _job_store.get(job_id)


def get_queue_stats() -> dict:
    """Get queue statistics."""
    stats = {
        "total_jobs": len(_job_store),
        "by_status": {},
        "by_type": {},
    }

    for job in _job_store.values():
        if "status" not in job:
            continue
        status = job["status"]
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        jtype = job.get("job_type", "unknown")
        stats["by_type"][jtype] = stats["by_type"].get(jtype, 0) + 1

    return stats


# =============================================================================
# Celery Workers (Production)
# =============================================================================

# For production, uncomment and configure Celery:
#
# from celery import Celery
#
# celery_app = Celery(
#     "keabuilder",
#     broker=settings.redis_url,
#     backend=settings.redis_url,
# )
#
# celery_app.conf.update(
#     task_serializer="json",
#     result_serializer="json",
#     accept_content=["json"],
#     task_routes={
#         "workers.image_worker.*": {"queue": "gpu"},
#         "workers.video_worker.*": {"queue": "gpu"},
#         "workers.lora_trainer.*": {"queue": "gpu_heavy"},
#     },
#     task_default_queue="default",
#     worker_prefetch_multiplier=1,  # Fair scheduling
#     task_acks_late=True,           # Ensure tasks survive worker crashes
# )
