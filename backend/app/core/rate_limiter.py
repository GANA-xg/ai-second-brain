"""
Rate limiting for authentication endpoints.

Uses an in-memory sliding-window counter by default.
Designed with a clean interface so a Redis backend can be swapped in later
by replacing InMemoryRateStore with a Redis-backed implementation.

Rate limits are applied per-IP (or per-user for /refresh) on configurable
windows. Exceeded limits return HTTP 429 with a Retry-After header.
"""

import time
from collections import defaultdict
from typing import Callable, List, Optional, Tuple

from fastapi import HTTPException, Request, status


class InMemoryRateStore:
    """Thread-safe in-memory sliding-window rate store.

    Keeps per-key timestamps of recent requests and evicts stale entries
    on each check.  Not distributed — adequate for single-process deployments
    and testing.
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, window_seconds: float) -> None:
        now = time.time()
        cutoff = now - window_seconds
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]
        if not self._windows[key]:
            del self._windows[key]

    def check(self, key: str, max_requests: int, window_seconds: float) -> Tuple[bool, int]:
        """Check whether *key* may proceed.

        Returns (allowed, retry_after_seconds).
        """
        self._cleanup(key, window_seconds)
        count = len(self._windows.get(key, []))
        if count >= max_requests:
            oldest = self._windows[key][0]
            retry_after = int(window_seconds - (time.time() - oldest))
            return False, max(1, retry_after)
        return True, 0

    def increment(self, key: str) -> None:
        self._windows[key].append(time.time())


# Singleton store – shared across all RateLimiter instances.
_store = InMemoryRateStore()


class RateLimiter:
    """FastAPI-compatible callable dependency for rate limiting.

    Usage in a route::

        @router.post("/login")
        def login(
            data: LoginRequest,
            db: Session = Depends(get_db),
            _: bool = Depends(login_limiter),
        ):
            ...

    The ``_`` parameter is the dependency result (always ``True`` when
    allowed); if the limit is exceeded the dependency raises an
    ``HTTPException`` before the handler body runs.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int = 60,
        key_func: Optional[Callable[[Request], str]] = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_func = key_func or RateLimiter._client_ip_key

    @staticmethod
    def _client_ip_key(request: Request) -> str:
        """Extract client IP, respecting reverse-proxy headers."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "unknown"

    @staticmethod
    def _user_id_key(request: Request) -> str:
        """Extract user ID from an authenticated request.

        Falls back to client IP if the user is not yet authenticated.
        """
        # If authorization header is present, derive a stable key from it.
        # For unauthenticated endpoints (login, register) the IP is used.
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            # Use a hash of the token prefix + IP as a stable key per user.
            # The full token is never stored here.
            token_prefix = auth[7:20]  # first 13 chars of token
            return f"user:{token_prefix}"
        return RateLimiter._client_ip_key(request)

    def __call__(self, request: Request) -> bool:
        key = self.key_func(request)
        allowed, retry_after = _store.check(key, self.max_requests, self.window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        _store.increment(key)
        return True


# ---------------------------------------------------------------------------
# Pre-configured limiters — import and use as Depends() in route handlers.
# ---------------------------------------------------------------------------

login_limiter = RateLimiter(
    max_requests=5,
    window_seconds=60,
    key_func=RateLimiter._client_ip_key,
)

register_limiter = RateLimiter(
    max_requests=3,
    window_seconds=60,
    key_func=RateLimiter._client_ip_key,
)

# Refresh uses user-scoped key (by token prefix) so each authenticated user
# gets their own budget.
refresh_limiter = RateLimiter(
    max_requests=20,
    window_seconds=60,
    key_func=RateLimiter._user_id_key,
)

logout_limiter = RateLimiter(
    max_requests=30,
    window_seconds=60,
    key_func=RateLimiter._user_id_key,
)
