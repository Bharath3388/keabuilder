"""Monitoring and metrics utilities."""

import time
import structlog
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger()

# Prometheus metrics
REQUEST_COUNT = Counter(
    "keabuilder_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "keabuilder_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"]
)

AI_CALL_COUNT = Counter(
    "keabuilder_ai_calls_total",
    "Total AI provider calls",
    ["provider", "type", "status"]
)

AI_CALL_LATENCY = Histogram(
    "keabuilder_ai_call_duration_seconds",
    "AI provider call latency",
    ["provider", "type"]
)

FALLBACK_COUNT = Counter(
    "keabuilder_fallback_total",
    "Total fallback invocations",
    ["service", "fallback_type"]
)

QUEUE_DEPTH = Gauge(
    "keabuilder_queue_depth",
    "Current job queue depth",
    ["queue_name"]
)

ACTIVE_JOBS = Gauge(
    "keabuilder_active_jobs",
    "Currently processing jobs",
    ["job_type"]
)


class Timer:
    """Context manager for timing operations."""

    def __init__(self, name: str, extra: dict = None):
        self.name = name
        self.extra = extra or {}

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start
        logger.info(
            f"{self.name} completed",
            duration_ms=round(self.elapsed * 1000, 2),
            **self.extra,
        )
