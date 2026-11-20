import pytest

import auth.rate_limit as rate_limit
from auth.rate_limit import LoginLimiter


@pytest.fixture
def clock(monkeypatch):
    """Fake monotonic clock so the window can be tested without sleeping."""
    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    return now


def test_blocks_after_max_failures(clock):
    limiter = LoginLimiter(max_failures=3, window_seconds=60)
    for _ in range(2):
        limiter.record_failure("a")
    assert limiter.retry_after("a") == 0
    limiter.record_failure("a")
    assert 0 < limiter.retry_after("a") <= 61


def test_keys_are_independent(clock):
    limiter = LoginLimiter(max_failures=1, window_seconds=60)
    limiter.record_failure("a")
    assert limiter.retry_after("a") > 0
    assert limiter.retry_after("b") == 0


def test_unblocks_after_the_window_and_cleans_up(clock):
    limiter = LoginLimiter(max_failures=2, window_seconds=60)
    limiter.record_failure("a")
    limiter.record_failure("a")
    clock[0] += 61
    assert limiter.retry_after("a") == 0
    assert "a" not in limiter._failures


def test_reset_clears_failures(clock):
    limiter = LoginLimiter(max_failures=1, window_seconds=60)
    limiter.record_failure("a")
    limiter.reset("a")
    assert limiter.retry_after("a") == 0
