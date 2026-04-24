"""KeaBuilder configuration management."""

import os
import secrets
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    # App
    app_name: str = "KeaBuilder"
    app_env: str = "development"
    app_secret_key: str = ""
    app_port: int = 8000
    port: int = 8000  # Railway injects PORT env var
    cors_origins: str = "http://localhost:3000"

    # LLM — Groq (free tier)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # LLM — Ollama (local fallback)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # Image — Hugging Face (free tier, fallback)
    hf_api_token: str = ""
    hf_image_model: str = "stabilityai/stable-diffusion-xl-base-1.0"

    # Gemini / Google AI
    gemini_api_key: str = ""
    gemini_image_model: str = "imagen-4.0-fast-generate-001"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_text_model: str = "gemini-2.0-flash"

    # Voice — edge-tts (free)
    tts_provider: str = "edge-tts"
    tts_default_voice: str = "en-US-AriaNeural"

    # Storage
    storage_provider: str = "local"
    storage_local_path: str = "./storage"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = "keabuilder-assets"
    aws_region: str = "us-east-1"

    # Database
    database_url: str = "sqlite:///./keabuilder.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # ChromaDB
    chroma_persist_dir: str = "./storage/chromadb"

    # Rate Limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 10
    trusted_proxies: list[str] = []  # IPs of trusted reverse proxies (e.g., ["10.0.0.0/8"])

    # API Authentication
    api_keys: str = ""  # Comma-separated API keys for client auth

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @model_validator(mode="after")
    def _validate_secret_key(self):
        if not self.app_secret_key:
            if self.app_env == "production":
                raise ValueError("APP_SECRET_KEY must be set in production")
            self.app_secret_key = secrets.token_urlsafe(32)
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def api_key_list(self) -> list[str]:
        if not self.api_keys:
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
