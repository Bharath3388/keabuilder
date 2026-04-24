"""Q5: Resilience — Circuit Breaker, Retry, Fallback, and Degraded Mode.

Wraps all external AI calls with resilience patterns.
Uses a simple circuit breaker implementation and tenacity for retries.
"""

import time
import asyncio
import structlog
from typing import Callable, TypeVar, Any
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from utils.monitoring import FALLBACK_COUNT

logger = structlog.get_logger()

T = TypeVar("T")

# =============================================================================
# Simple Circuit Breaker (no external dependency issues)
# =============================================================================

class SimpleCircuitBreaker:
    """Minimal circuit breaker implementation."""

    def __init__(self, name: str, fail_max: int = 5, reset_timeout: float = 30.0):
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._fail_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"  # closed, open, half-open

    @property
    def current_state(self) -> str:
        if self._state == "open":
            if time.time() - self._last_failure_time > self.reset_timeout:
                self._state = "half-open"
        return self._state

    @property
    def fail_counter(self) -> int:
        return self._fail_count

    def record_success(self):
        self._fail_count = 0
        self._state = "closed"

    def record_failure(self):
        self._fail_count += 1
        self._last_failure_time = time.time()
        if self._fail_count >= self.fail_max:
            self._state = "open"
            logger.warning(f"Circuit breaker OPENED for {self.name}")


_breakers: dict[str, SimpleCircuitBreaker] = {}


def get_breaker(service_name: str) -> SimpleCircuitBreaker:
    """Get or create a circuit breaker for a service."""
    if service_name not in _breakers:
        _breakers[service_name] = SimpleCircuitBreaker(
            name=service_name,
            fail_max=5,
            reset_timeout=30,
        )
    return _breakers[service_name]


# =============================================================================
# Retry Decorator
# =============================================================================

def with_retry(func):
    """Retry a function up to 3 times with exponential backoff."""
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    return wrapper


# =============================================================================
# Call With Fallback (Main Entry Point)
# =============================================================================

async def call_with_fallback(
    primary: Callable,
    fallback: Callable,
    service_name: str = "default",
    timeout: float = 15.0,
) -> Any:
    """Execute primary function with circuit breaker, retry, and fallback.

    Flow:
    1. Check circuit breaker state
    2. Try primary with timeout
    3. On failure → try fallback
    4. On fallback failure → raise
    """
    breaker = get_breaker(service_name)

    # Try primary
    try:
        if breaker.current_state == "open":
            logger.warning(f"Circuit breaker OPEN for {service_name}, skipping primary")
            raise Exception(f"Circuit breaker open for {service_name}")

        result = await _execute_with_timeout(primary, timeout)
        breaker.record_success()
        return result

    except Exception as primary_err:
        breaker.record_failure()

        logger.warning(
            f"Primary failed for {service_name}, trying fallback",
            error=str(primary_err),
        )
        FALLBACK_COUNT.labels(service=service_name, fallback_type="secondary").inc()

        # Try fallback
        try:
            result = await _execute_with_timeout(fallback, timeout)
            return result
        except Exception as fallback_err:
            logger.error(
                f"Fallback also failed for {service_name}",
                primary_error=str(primary_err),
                fallback_error=str(fallback_err),
            )
            FALLBACK_COUNT.labels(service=service_name, fallback_type="degraded").inc()
            raise fallback_err


async def _execute_with_timeout(func: Callable, timeout: float) -> Any:
    """Execute a function with a timeout."""
    try:
        return await asyncio.wait_for(func(), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {timeout}s")


# =============================================================================
# Service Health Status
# =============================================================================

def get_service_health() -> dict:
    """Get current health status of all circuit breakers."""
    return {
        name: {
            "state": breaker.current_state,
            "fail_count": breaker.fail_counter,
        }
        for name, breaker in _breakers.items()
    }
