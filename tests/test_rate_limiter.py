"""Tests for the in-memory sliding-window rate limiter."""
import time
from unittest.mock import patch

import pytest

from app.rate_limiter import RateLimiter


@pytest.fixture
def limiter():
    return RateLimiter()


async def test_allows_within_limit(limiter):
    """N requests under limit all return True."""
    for _ in range(5):
        assert await limiter.check("token-a", 5) is True


async def test_blocks_over_limit(limiter):
    """Request N+1 returns False."""
    for _ in range(5):
        await limiter.check("token-a", 5)
    assert await limiter.check("token-a", 5) is False


async def test_window_slides(limiter):
    """After 60s, old requests expire and new ones are allowed."""
    base = time.monotonic()
    with patch("time.monotonic", return_value=base):
        for _ in range(5):
            await limiter.check("token-a", 5)

    # Advance past the 60-second window
    with patch("time.monotonic", return_value=base + 61):
        assert await limiter.check("token-a", 5) is True


async def test_window_does_not_slide_prematurely(limiter):
    """At exactly 59s, old requests should still count."""
    base = time.monotonic()
    with patch("time.monotonic", return_value=base):
        for _ in range(5):
            await limiter.check("token-a", 5)

    # 59 seconds later — still within the 60-second window
    with patch("time.monotonic", return_value=base + 59):
        assert await limiter.check("token-a", 5) is False


async def test_different_tokens_independent(limiter):
    """Token A's limit doesn't affect token B."""
    for _ in range(5):
        await limiter.check("token-a", 5)
    assert await limiter.check("token-a", 5) is False
    assert await limiter.check("token-b", 5) is True


async def test_cleanup_removes_stale(limiter):
    """cleanup() removes tokens with no recent activity."""
    base = time.monotonic()
    with patch("time.monotonic", return_value=base):
        await limiter.check("token-a", 10)

    # CLEANUP_IDLE_SECONDS is 1 hour — long enough that a sustained-rate
    # cap (checked via check_multi with an hour-long window) survives
    # short pauses instead of silently resetting.
    with patch("time.monotonic", return_value=base + limiter.CLEANUP_IDLE_SECONDS + 1):
        await limiter.cleanup()
        assert "token-a" not in limiter._windows


async def test_cleanup_keeps_recently_idle(limiter):
    """A token idle for only a minute survives cleanup (not yet stale)."""
    base = time.monotonic()
    with patch("time.monotonic", return_value=base):
        await limiter.check("token-a", 10)

    with patch("time.monotonic", return_value=base + 61):
        await limiter.cleanup()
        assert "token-a" in limiter._windows


async def test_cleanup_keeps_active(limiter):
    """Active tokens survive cleanup."""
    await limiter.check("token-a", 10)
    await limiter.cleanup()
    assert "token-a" in limiter._windows


async def test_limit_of_one(limiter):
    """RPM=1 allows exactly one request."""
    assert await limiter.check("token-a", 1) is True
    assert await limiter.check("token-a", 1) is False


async def test_partial_window_expiry(limiter):
    """Only old entries expire; recent ones remain and count."""
    base = time.monotonic()

    # 3 requests at t=0
    with patch("time.monotonic", return_value=base):
        for _ in range(3):
            await limiter.check("token-a", 5)

    # 2 more requests at t=30 (within window)
    with patch("time.monotonic", return_value=base + 30):
        for _ in range(2):
            await limiter.check("token-a", 5)

    # At t=61, the first 3 expired but the 2 from t=30 are still in window
    with patch("time.monotonic", return_value=base + 61):
        assert await limiter.check("token-a", 5) is True  # 2 in window, under 5
        assert await limiter.check("token-a", 5) is True  # 3 in window
        assert await limiter.check("token-a", 5) is True  # 4 in window
        assert await limiter.check("token-a", 5) is False  # 5 = limit, next blocked


# ---------------------------------------------------------------------------
# check_multi — dual burst + sustained-rate windows
# ---------------------------------------------------------------------------

async def test_check_multi_allows_within_both_limits(limiter):
    for _ in range(10):
        assert await limiter.check_multi("token-a", [(60, 10), (3600, 100)]) is True


async def test_check_multi_blocks_on_short_window_even_under_long_limit(limiter):
    """Bursting past the per-minute cap blocks even though the hourly
    budget has plenty of headroom left."""
    for _ in range(10):
        await limiter.check_multi("token-a", [(60, 10), (3600, 100)])
    assert await limiter.check_multi("token-a", [(60, 10), (3600, 100)]) is False


async def test_check_multi_blocks_on_long_window_even_under_short_limit(limiter):
    """Sustained use within the per-minute cap still gets capped once the
    hourly budget runs out."""
    base = time.monotonic()
    # 20 requests, well within the 60/min burst cap, spread out so the
    # short window never trips, but exhausting the tiny hourly budget.
    for i in range(20):
        with patch("time.monotonic", return_value=base + i * 3):
            await limiter.check_multi("token-a", [(60, 60), (3600, 20)])

    with patch("time.monotonic", return_value=base + 60):
        assert await limiter.check_multi("token-a", [(60, 60), (3600, 20)]) is False


async def test_check_multi_long_window_recovers_after_expiry(limiter):
    base = time.monotonic()
    with patch("time.monotonic", return_value=base):
        for _ in range(5):
            await limiter.check_multi("token-a", [(60, 60), (3600, 5)])
        assert await limiter.check_multi("token-a", [(60, 60), (3600, 5)]) is False

    with patch("time.monotonic", return_value=base + 3601):
        assert await limiter.check_multi("token-a", [(60, 60), (3600, 5)]) is True
