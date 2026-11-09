"""
Sliding-Window In-Memory Rate Limiter for Telegram Mini App API.
Protects against spam, botting, and duplicate clicking.
"""
import time
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, HTTPException, status


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter per client key (telegram_id or IP).
    """
    def __init__(self, max_requests: int = 30, window_seconds: int = 10):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _cleanup_old(self, now: float):
        """Purge records older than window to prevent memory accumulation."""
        if now - self._last_cleanup < 60:
            return
        threshold = now - self.window_seconds
        stale_keys = []
        for key, timestamps in self._history.items():
            valid_ts = [t for t in timestamps if t > threshold]
            if valid_ts:
                self._history[key] = valid_ts
            else:
                stale_keys.append(key)
        for sk in stale_keys:
            self._history.pop(sk, None)
        self._last_cleanup = now

    def check(self, key: str):
        """Check if request is allowed. Raises 429 if limit exceeded."""
        now = time.time()
        self._cleanup_old(now)
        threshold = now - self.window_seconds
        
        # Filter timestamps within current window
        history = [t for t in self._history[key] if t > threshold]
        
        if len(history) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - history[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Juda ko'p so'rov yuborildi. Iltimos {retry_after} soniya kuting.",
                headers={"Retry-After": str(max(1, retry_after))}
            )
        
        history.append(now)
        self._history[key] = history


# Global rate limiter instance: 30 requests per 10 seconds
global_rate_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=10)


async def rate_limit_dependency(request: Request):
    """
    FastAPI dependency for rate limiting by IP (or client key).
    User-level rate limiting is further enforced inside authenticated endpoints.
    """
    client_ip = request.client.host if request.client else "unknown"
    global_rate_limiter.check(client_ip)
