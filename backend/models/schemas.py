"""Pydantic schemas for all API request/response models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


# =============================================================================
# Q1: Lead Classification
# =============================================================================

class LeadClassification(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class LeadInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr = Field(...)
    company: Optional[str] = None
    company_size: Optional[str] = None
    budget_range: Optional[str] = None
    timeline: Optional[str] = None
    use_case: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    source: Optional[str] = None


class LeadClassificationResult(BaseModel):
    lead_id: str
    classification: LeadClassification
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    missing_signals: list[str] = []
    follow_up_questions: list[str] = []
    suggested_response: str
    crm_tags: list[str] = []
    assigned_to: Optional[str] = None
    next_action: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Q2: Multi-Modal Content Generation
# =============================================================================

class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"


class Dimensions(BaseModel):
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)


class GenerateRequest(BaseModel):
    type: MediaType
    prompt: str = Field(..., min_length=1, max_length=2000)
    style: Optional[str] = None
    dimensions: Optional[Dimensions] = None
    voice_id: Optional[str] = None
    user_id: str
    workspace_id: str


class AssetMetadata(BaseModel):
    type: MediaType
    dimensions: Optional[Dimensions] = None
    size_bytes: int = 0
    duration_seconds: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GenerateResponse(BaseModel):
    asset_id: str
    status: str = "completed"
    url: str
    thumbnail_url: Optional[str] = None
    provider_used: str
    metadata: AssetMetadata
    script: Optional[str] = None  # Generated voiceover script for voice content


# =============================================================================
# Q3: LoRA Integration
# =============================================================================

class LoRATrainRequest(BaseModel):
    user_id: str
    workspace_id: str
    lora_name: str = Field(..., min_length=1, max_length=100)
    trigger_token: str = Field(default="ohwx person")
    training_steps: int = Field(default=1500, ge=500, le=5000)


class LoRATrainResponse(BaseModel):
    job_id: str
    status: str = "training"
    lora_id: str
    estimated_time_minutes: int = 15
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoRAGenerateRequest(BaseModel):
    user_id: str
    workspace_id: str
    lora_id: str
    prompt: str = Field(..., min_length=1, max_length=2000)
    use_brand_style: bool = True
    num_inference_steps: int = Field(default=30, ge=10, le=50)
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)


# =============================================================================
# Q4: Similarity Search
# =============================================================================

class EmbedType(str, Enum):
    TEXT = "text"
    CLIP = "clip"
    FACE = "face"


class SimilaritySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    workspace_id: str
    embed_type: EmbedType = EmbedType.TEXT
    top_k: int = Field(default=10, ge=1, le=100)


class SimilarityResult(BaseModel):
    asset_id: str
    similarity: float
    metadata: dict = {}


class SimilaritySearchResponse(BaseModel):
    results: list[SimilarityResult]
    query_time_ms: float
    total_results: int


# =============================================================================
# Q6: Assets
# =============================================================================

class AssetListRequest(BaseModel):
    workspace_id: str
    type: Optional[MediaType] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class Asset(BaseModel):
    asset_id: str
    workspace_id: str
    type: MediaType
    url: str
    thumbnail_url: Optional[str] = None
    prompt: Optional[str] = None
    provider: str
    tags: list[str] = []
    created_at: datetime


# =============================================================================
# Health
# =============================================================================

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    services: dict = {}
