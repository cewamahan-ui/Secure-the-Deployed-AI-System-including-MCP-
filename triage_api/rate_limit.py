"""Per-token rate limiter.

Lesson reference: Monday Lesson 6 (rate_limit.py).
429 comes from this module after 5 calls in a 60-second window per
authenticated subject (the `sub` claim of the JWT).

State is in-process memory. The trade-off is honest: a restart resets
all buckets. For multi-replica deployments swap this for a Redis-backed
counter - the FastAPI contract (429 + Retry-After) does not change.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, status

# module-level state - one deque per subject
_buckets: dict[str, deque[float]] = {}
_lock = Lock()


def check(subject: str, max_calls: int, window_seconds: int) -> None:
    """Raise 429 if `subject` has made more than `max_calls` in `window_seconds`.

    Sliding window: timestamps older than `now - window_seconds` are dropped.
    The most recent timestamp is then added.
    """
    if not subject:
        # No subject means no auth, which should already have been rejected.
        # Defensive: refuse rather than silently bypass.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="rate limit requires an authenticated subject",
        )

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = _buckets.setdefault(subject, deque())
        # drop expired
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_calls:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limited",
                    "limit": max_calls,
                    "window_seconds": window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


def reset_for_tests() -> None:
    """Test-only helper. Not part of the public API."""
    with _lock:
        _buckets.clear()