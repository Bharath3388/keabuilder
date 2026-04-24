"""KeaBuilder — FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from config import get_settings
from models.database import init_db
from api.routes import leads, generate, lora, search, health, assets
from api.middleware.rate_limiter import RateLimitMiddleware
from api.middleware.auth import require_api_key


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    init_db()

    # Ensure storage directories exist
    storage_path = Path(settings.storage_local_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "chromadb").mkdir(exist_ok=True)

    yield

    # Shutdown (cleanup if needed)


app = FastAPI(
    title="KeaBuilder API",
    description="AI-powered SaaS platform for funnels, lead capture, and automation",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Middleware order: last added = outermost (first to run)
# CORS must be outermost so preflight OPTIONS are handled before anything else.

# Rate limiting (inner — runs after CORS)
app.add_middleware(RateLimitMiddleware)

# CORS (outer — runs first)
cors_kwargs: dict = dict(
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
# Allow Vercel preview deploys via regex (set CORS_ORIGIN_REGEX env var, or use default)
origin_regex = settings.cors_origin_regex or r"https://.*\.vercel\.app"
cors_kwargs["allow_origin_regex"] = origin_regex
app.add_middleware(CORSMiddleware, **cors_kwargs)

@app.get("/")
async def root():
    """Root endpoint — basic service info."""
    return {"service": "KeaBuilder API", "version": "1.0.0", "docs": "/docs"}


# Static files — only serve workspace asset files, NOT internal dirs (chromadb, loras)
# Blocked directories that should never be served
_BLOCKED_STORAGE_DIRS = {"chromadb", "loras"}
storage_path = Path(settings.storage_local_path)
storage_path.mkdir(parents=True, exist_ok=True)


@app.get("/storage/{file_path:path}")
async def serve_storage_file(file_path: str):
    """Serve storage files with security checks (public — no API key needed for assets)."""
    # Block access to internal directories
    parts = Path(file_path).parts
    if not parts or parts[0] in _BLOCKED_STORAGE_DIRS:
        raise HTTPException(status_code=404, detail="Not found")

    resolved = (storage_path / file_path).resolve()
    # Prevent path traversal
    if not str(resolved).startswith(str(storage_path.resolve())):
        raise HTTPException(status_code=404, detail="Not found")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(resolved)

# Routes
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(leads.router, prefix="/api/v1/leads", tags=["Lead Intelligence"])
app.include_router(generate.router, prefix="/api/v1", tags=["Content Generation"])
app.include_router(lora.router, prefix="/api/v1/lora", tags=["LoRA Brand Kit"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Similarity Search"])
app.include_router(assets.router, prefix="/api/v1/assets", tags=["Asset Management"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
