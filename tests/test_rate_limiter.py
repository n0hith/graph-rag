"""Tests for the requests-per-minute / per-day limiter and backoff."""

import json

import pytest

from src.llm.rate_limiter import DailyLimitReached, RateLimiter, backoff_delay


class FakeClock:
    """A clock that only moves when `sleep` is called, so tests run instantly."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_limiter(rpm=3, rpd=0, state_file=None, day="2026-10-14"):
    clock = FakeClock()
    days = {"today": day}
    limiter = RateLimiter(
        rpm, rpd, state_file, clock=clock, sleep=clock.sleep, today=lambda: days["today"]
    )
    return limiter, clock, days


def test_requests_under_rpm_do_not_wait():
    limiter, clock, _ = make_limiter(rpm=3)
    for _ in range(3):
        limiter.acquire("m")
    assert clock.sleeps == []


def test_request_over_rpm_waits_until_window_frees():
    limiter, clock, _ = make_limiter(rpm=3)
    for _ in range(3):
        limiter.acquire("m")
        clock.now += 10  # requests at t=0, 10, 20
    limiter.acquire("m")  # at t=30, must wait until t=60
    assert clock.now == pytest.approx(60.0)


def test_rpm_is_tracked_per_model():
    limiter, clock, _ = make_limiter(rpm=1)
    limiter.acquire("model-a")
    limiter.acquire("model-b")
    assert clock.sleeps == []


def test_zero_means_unlimited():
    limiter, clock, _ = make_limiter(rpm=0, rpd=0)
    for _ in range(100):
        limiter.acquire("m")
    assert clock.sleeps == []


def test_daily_limit_raises_and_resets_next_day(tmp_path):
    state = tmp_path / "quota.json"
    limiter, _, days = make_limiter(rpm=0, rpd=2, state_file=state)
    limiter.acquire("m")
    limiter.acquire("m")
    with pytest.raises(DailyLimitReached):
        limiter.acquire("m")
    days["today"] = "2026-10-15"
    limiter.acquire("m")
    assert limiter.used_today("m") == 1


def test_daily_count_survives_restart(tmp_path):
    state = tmp_path / "quota.json"
    first, _, _ = make_limiter(rpm=0, rpd=2, state_file=state)
    first.acquire("m")
    first.acquire("m")
    second, _, _ = make_limiter(rpm=0, rpd=2, state_file=state)  # a new run, same day
    with pytest.raises(DailyLimitReached):
        second.acquire("m")
    assert json.loads(state.read_text())["counts"]["m"] == 2


def test_corrupt_state_file_is_treated_as_zero(tmp_path):
    state = tmp_path / "quota.json"
    state.write_text("not json")
    limiter, _, _ = make_limiter(rpm=0, rpd=1, state_file=state)
    limiter.acquire("m")
    assert limiter.used_today("m") == 1


def test_backoff_grows_and_is_capped():
    assert backoff_delay(0, base=2, cap=60, rng=lambda: 0.0) == 1.0
    assert backoff_delay(0, base=2, cap=60, rng=lambda: 1.0) == 2.0
    assert backoff_delay(3, base=2, cap=60, rng=lambda: 1.0) == 16.0
    assert backoff_delay(10, base=2, cap=60, rng=lambda: 1.0) == 60.0
