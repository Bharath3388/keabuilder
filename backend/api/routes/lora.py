"""Q3: LoRA management API routes."""

import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from models.schemas import LoRATrainRequest, LoRATrainResponse, LoRAGenerateRequest
from models.database import get_db, LoRARecord
from services.lora_service import (
    start_lora_training,
    generate_with_lora,
    list_user_loras,
)
from utils.storage import get_storage
from api.middleware.auth import require_api_key

router = APIRouter()


@router.post("/train", response_model=LoRATrainResponse)
async def train_lora(
    user_id: str = Form(...),
    workspace_id: str = Form(...),
    lora_name: str = Form(...),
    trigger_token: str = Form("ohwx person"),
    training_steps: int = Form(1500),
    images: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Upload reference images and start LoRA training."""
    if len(images) < 5:
        raise HTTPException(400, "At least 5 reference images are required (10-20 recommended)")
    if len(images) > 30:
        raise HTTPException(400, "Maximum 30 reference images allowed")

    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}

    # Save uploaded images
    storage = get_storage()
    image_paths = []
    for img in images:
        # Validate content type
        if img.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                400,
                f"File {img.filename} has unsupported type '{img.content_type}'. "
                f"Allowed: JPEG, PNG, WebP, BMP, TIFF",
            )
        content = await img.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit per image
            raise HTTPException(400, f"Image {img.filename} exceeds 10MB limit")
        # Validate image magic bytes
        if not (
            content[:8].startswith(b"\x89PNG")      # PNG
            or content[:2] == b"\xff\xd8"            # JPEG
            or content[:4] == b"RIFF"                # WebP
            or content[:2] in (b"BM",)               # BMP
            or content[:4] in (b"II\x2a\x00", b"MM\x00\x2a")  # TIFF
        ):
            raise HTTPException(400, f"File {img.filename} is not a valid image")
        # Sanitize filename
        safe_filename = f"{uuid.uuid4().hex[:8]}.png"
        path = await storage.upload(content, workspace_id, "lora_training", safe_filename)
        image_paths.append(path)

    # Start training
    result = await start_lora_training(
        user_id=user_id,
        workspace_id=workspace_id,
        lora_name=lora_name,
        image_paths=image_paths,
        trigger_token=trigger_token,
        training_steps=training_steps,
    )

    # Persist record
    lora_record = LoRARecord(
        id=result["lora_id"],
        user_id=user_id,
        workspace_id=workspace_id,
        name=lora_name,
        trigger_token=trigger_token,
        status=result["status"],
        training_steps=training_steps,
    )
    db.add(lora_record)
    db.commit()

    return LoRATrainResponse(
        job_id=result["job_id"],
        status=result["status"],
        lora_id=result["lora_id"],
        estimated_time_minutes=result.get("estimated_time_minutes", 15),
    )


@router.post("/generate")
async def generate_with_lora_model(req: LoRAGenerateRequest, db: Session = Depends(get_db), _key: str = Depends(require_api_key)):
    """Generate an image using a trained LoRA model."""
    # Verify LoRA exists
    lora = db.query(LoRARecord).filter(
        LoRARecord.id == req.lora_id,
        LoRARecord.user_id == req.user_id,
    ).first()

    if not lora:
        raise HTTPException(404, f"LoRA {req.lora_id} not found")

    try:
        result = await generate_with_lora(
            user_id=req.user_id,
            workspace_id=req.workspace_id,
            lora_id=req.lora_id,
            prompt=req.prompt,
            num_inference_steps=req.num_inference_steps,
            guidance_scale=req.guidance_scale,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/list/{user_id}")
async def list_loras(user_id: str, _key: str = Depends(require_api_key)):
    """List all LoRA models for a user."""
    loras = list_user_loras(user_id)
    return {"loras": loras, "count": len(loras)}


@router.get("/status/{lora_id}")
async def get_lora_status(lora_id: str, user_id: str, db: Session = Depends(get_db), _key: str = Depends(require_api_key)):
    """Check the status of a LoRA training job."""
    lora = db.query(LoRARecord).filter(
        LoRARecord.id == lora_id,
        LoRARecord.user_id == user_id,
    ).first()
    if not lora:
        raise HTTPException(404, "LoRA not found")

    return {
        "lora_id": lora.id,
        "name": lora.name,
        "status": lora.status,
        "trigger_token": lora.trigger_token,
        "created_at": lora.created_at.isoformat() if lora.created_at else None,
    }
