"""Per-token sliding-window rate limiter (in-memory)."""
import asyncio
import time
from collections import deque


class RateLimiter:
    WINDOW_SECONDS = 60.0
    # How long an idle token's history is kept around before cleanup() drops
    # it — must be at least as long as the widest window ever passed to
    # check_multi(), or a sustained-rate cap effectively resets on any pause
    # longer than this.
    CLEANUP_IDLE_SECONDS = 3600.0

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, token_id: str, limit_rpm: int) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        return await self.check_multi(token_id, [(self.WINDOW_SECONDS, limit_rpm)])

    async def check_multi(self, token_id: str, limits: list[tuple[float, int]]) -> bool:
        """Return True only if the request is allowed under EVERY given
        (window_seconds, limit) constraint — e.g. a short burst allowance
        plus a lower sustained-rate cap over a longer window."""
        now = time.monotonic()
        max_window = max(window for window, _ in limits)

        async with self._lock:
            dq = self._windows.setdefault(token_id, deque())
            # Drop timestamps outside the widest window in play
            cutoff = now - max_window
            while dq and dq[0] < cutoff:
                dq.popleft()

            for window, limit in limits:
                window_start = now - window
                count = sum(1 for t in dq if t >= window_start)
                if count >= limit:
                    return False

            dq.append(now)
            return True

    async def cleanup(self) -> None:
        """Remove entries for tokens with no recent requests (call periodically)."""
        now = time.monotonic()
        window_start = now - self.CLEANUP_IDLE_SECONDS
        async with self._lock:
            stale = [tid for tid, dq in self._windows.items() if not dq or dq[-1] < window_start]
            for tid in stale:
                del self._windows[tid]


rate_limiter = RateLimiter()
