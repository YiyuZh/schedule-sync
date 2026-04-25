from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request

from app.core.config import get_settings
from app.core.response import AppException


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, *, max_attempts: int, window_seconds: int) -> None:
        now = time.monotonic()
        bucket = self._events[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= max_attempts:
            raise AppException("请求过于频繁，请稍后再试", code=4290, status_code=429)
        bucket.append(now)


rate_limiter = InMemoryRateLimiter()


def check_auth_rate_limit(request: Request, action: str, identifier: str) -> None:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    normalized_identifier = identifier.strip().lower() if identifier else "unknown"
    key = f"auth:{action}:{client_host}:{normalized_identifier}"
    rate_limiter.check(
        key,
        max_attempts=max(1, settings.auth_rate_limit_max_attempts),
        window_seconds=max(1, settings.auth_rate_limit_window_seconds),
    )
