"""Storage utilities — local filesystem (dev) or S3 (prod)."""

import os
import re
import uuid
import hashlib
import aiofiles
from pathlib import Path
from config import get_settings

settings = get_settings()

# Regex: only allow alphanumeric, hyphens, underscores, dots (no slashes, no ..)
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _sanitize_path_component(value: str) -> str:
    """Sanitize a single path component to prevent traversal attacks."""
    if not value:
        raise ValueError("Empty path component")
    # Reject if it contains any path separators or parent references
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"Invalid path component: {value!r}")
    # Strip to basename as extra safety
    value = os.path.basename(value)
    if not value or not _SAFE_PATH_RE.match(value):
        raise ValueError(f"Invalid path component: {value!r}")
    if value in (".", ".."):
        raise ValueError(f"Invalid path component: {value!r}")
    return value


def generate_asset_id(asset_type: str) -> str:
    """Generate a unique asset ID."""
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8]
    return f"ast_{date_str}_{asset_type}_{short_uuid}"


def hash_prompt(prompt: str) -> str:
    """Hash a prompt for caching/dedup."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


class LocalStorage:
    """Local filesystem storage for development."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _build_path(self, workspace_id: str, asset_type: str, filename: str) -> Path:
        workspace_id = _sanitize_path_component(workspace_id)
        asset_type = _sanitize_path_component(asset_type)
        filename = _sanitize_path_component(filename)
        path = self.base_path / workspace_id / asset_type
        path.mkdir(parents=True, exist_ok=True)
        full_path = (path / filename).resolve()
        # Final guard: ensure resolved path is still under base_path
        if not str(full_path).startswith(str(self.base_path.resolve())):
            raise ValueError("Path traversal detected")
        return full_path

    async def upload(
        self, data: bytes, workspace_id: str, asset_type: str, filename: str
    ) -> str:
        file_path = self._build_path(workspace_id, asset_type, filename)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)
        return f"/storage/{workspace_id}/{asset_type}/{filename}"

    async def download(self, workspace_id: str, asset_type: str, filename: str) -> bytes:
        file_path = self._build_path(workspace_id, asset_type, filename)
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    def get_url(self, workspace_id: str, asset_type: str, filename: str) -> str:
        return f"/storage/{workspace_id}/{asset_type}/{filename}"

    def exists(self, workspace_id: str, asset_type: str, filename: str) -> bool:
        return self._build_path(workspace_id, asset_type, filename).exists()


class S3Storage:
    """S3-compatible storage for production."""

    def __init__(self):
        import boto3
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self.bucket = settings.aws_s3_bucket

    async def upload(
        self, data: bytes, workspace_id: str, asset_type: str, filename: str
    ) -> str:
        workspace_id = _sanitize_path_component(workspace_id)
        asset_type = _sanitize_path_component(asset_type)
        filename = _sanitize_path_component(filename)
        key = f"{workspace_id}/{asset_type}/{filename}"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"

    async def download(self, workspace_id: str, asset_type: str, filename: str) -> bytes:
        workspace_id = _sanitize_path_component(workspace_id)
        asset_type = _sanitize_path_component(asset_type)
        filename = _sanitize_path_component(filename)
        key = f"{workspace_id}/{asset_type}/{filename}"
        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def get_url(self, workspace_id: str, asset_type: str, filename: str) -> str:
        workspace_id = _sanitize_path_component(workspace_id)
        asset_type = _sanitize_path_component(asset_type)
        filename = _sanitize_path_component(filename)
        key = f"{workspace_id}/{asset_type}/{filename}"
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,  # 1 hour
        )


def get_storage():
    """Factory: return the correct storage backend."""
    if settings.storage_provider == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_local_path)
