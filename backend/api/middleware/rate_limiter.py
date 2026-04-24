"""Rate limiting middleware."""

import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from config import get_settings

settings = get_settings()

# Maximum number of tracked IPs to prevent unbounded memory growth
_MAX_TRACKED_IPS = 10_000


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter. Use Redis-based limiter in production."""

    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.max_requests = settings.rate_limit_requests_per_minute
        self.window = 60  # seconds
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, respecting trusted proxy headers.

        Only trusts X-Forwarded-For if the direct connection is from a
        known trusted proxy, preventing IP spoofing.
        """
        direct_ip = request.client.host if request.client else "unknown"

        # Only trust forwarded headers from configured trusted proxies
        if settings.trusted_proxies and direct_ip in settings.trusted_proxies:
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()

            x_real_ip = request.headers.get("x-real-ip")
            if x_real_ip:
                return x_real_ip.strip()

        return direct_ip

    def _cleanup_stale_entries(self, now: float):
        """Periodically purge stale IPs to prevent memory leak."""
        if now - self._last_cleanup < self.window:
            return
        self._last_cleanup = now
        stale_keys = [
            ip for ip, timestamps in self.requests.items()
            if not timestamps or now - timestamps[-1] > self.window
        ]
        for key in stale_keys:
            del self.requests[key]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks, docs, and CORS preflight
        if request.url.path in ("/api/v1/health", "/docs", "/openapi.json"):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()

        # Periodic cleanup of stale entries
        self._cleanup_stale_entries(now)

        # Cap tracked IPs to prevent memory exhaustion
        if client_ip not in self.requests and len(self.requests) >= _MAX_TRACKED_IPS:
            return JSONResponse(
                status_code=503,
                content={"error": "Server busy", "detail": "Try again later"},
            )

        # Clean old entries for this IP
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if now - t < self.window
        ]

        if len(self.requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Max {self.max_requests} requests per minute",
                    "retry_after": self.window,
                },
            )

        self.requests[client_ip].append(now)
        return await call_next(request)
