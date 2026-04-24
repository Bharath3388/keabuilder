"""Image generation worker for async processing.

In production, this would run as a Celery worker on GPU instances.
"""

import structlog
from services.content_router import route_generation

logger = structlog.get_logger()


async def process_image_job(job_data: dict) -> dict:
    """Process an async image generation job."""
    result = await route_generation(
        media_type="image",
        prompt=job_data["prompt"],
        workspace_id=job_data["workspace_id"],
        user_id=job_data["user_id"],
        width=job_data.get("width", 1024),
        height=job_data.get("height", 1024),
        style=job_data.get("style"),
    )
    logger.info("Image job completed", asset_id=result["asset_id"])
    return result


# Celery task (production):
# @celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
# def process_image_task(self, job_data):
#     import asyncio
#     return asyncio.run(process_image_job(job_data))
