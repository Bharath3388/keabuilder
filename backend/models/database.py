"""Database models and connection management."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, JSON,
    create_engine, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from config import get_settings

Base = declarative_base()
settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,  # Never echo SQL to logs — use structured logging instead
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LeadRecord(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    company = Column(String)
    company_size = Column(String)
    budget_range = Column(String)
    timeline = Column(String)
    use_case = Column(Text)
    phone = Column(String)
    industry = Column(String)
    source = Column(String)
    classification = Column(String, index=True)
    confidence = Column(Float)
    reasoning = Column(Text)
    suggested_response = Column(Text)
    crm_tags = Column(JSON, default=list)
    assigned_to = Column(String)
    next_action = Column(String)
    raw_input = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AssetRecord(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String)
    prompt = Column(Text)
    prompt_hash = Column(String, index=True)
    provider = Column(String)
    style = Column(String)
    width = Column(Integer)
    height = Column(Integer)
    size_bytes = Column(Integer, default=0)
    duration_seconds = Column(Float)
    tags = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_assets_workspace_type", "workspace_id", "type"),
    )


class LoRARecord(Base):
    __tablename__ = "loras"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    trigger_token = Column(String, default="ohwx person")
    status = Column(String, default="pending")  # pending, training, ready, failed
    file_path = Column(String)
    training_steps = Column(Integer, default=1500)
    training_time_seconds = Column(Float)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)


class JobRecord(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=False)
    job_type = Column(String, nullable=False)  # image, video, voice, lora_train
    status = Column(String, default="queued")  # queued, processing, completed, failed
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
