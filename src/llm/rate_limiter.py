"""Client-side rate limiting (requests per minute and per day) and retry backoff."""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Gemini's per-day quotas reset at midnight Pacific time, so "today" is counted in that zone.
QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")


class DailyLimitReached(RuntimeError):
    """Raised when the per-day request budget is used up. Re-run after the quota resets."""


def pacific_today() -> str:
    """Today's date (YYYY-MM-DD) in the timezone where Gemini's daily quota resets."""
    return datetime.now(QUOTA_TIMEZONE).date().isoformat()


class RateLimiter:
    """Enforces a requests-per-minute and a requests-per-day budget, tracked per key (model).

    The per-minute window lives in memory. The per-day count is stored in a small JSON file,
    so it survives restarts and a long job that hits the cap can resume the next day.
    A limit of 0 disables that check.
    """

    def __init__(
        self,
        rpm: int,
        rpd: int,
        state_file: Path | None = None,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        today: Callable[[], str] = pacific_today,
    ) -> None:
        self.rpm = rpm
        self.rpd = rpd
        self.state_file = state_file
        self.window_seconds = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._today = today
        self._lock = threading.Lock()
        self._recent: dict[str, deque[float]] = {}
        self._memory_state: dict = {"date": None, "counts": {}}

    def acquire(self, key: str) -> None:
        """Block until a request for `key` is allowed, then record it.

        Raises:
            DailyLimitReached: if today's budget for `key` is already used up.
        """
        with self._lock:
            state = self._load_daily_state()
            used = state["counts"].get(key, 0)
            if self.rpd and used >= self.rpd:
                raise DailyLimitReached(
                    f"Daily request limit reached for {key} ({used}/{self.rpd} today, Pacific time). "
                    "Progress is saved; run the same command again after the quota resets."
                )
            self._wait_for_minute_slot(key)
            state["counts"][key] = used + 1
            self._save_daily_state(state)

    def used_today(self, key: str) -> int:
        """How many requests for `key` have been made today."""
        with self._lock:
            return self._load_daily_state()["counts"].get(key, 0)

    def _wait_for_minute_slot(self, key: str) -> None:
        if not self.rpm:
            return
        recent = self._recent.setdefault(key, deque())
        while True:
            now = self._clock()
            while recent and now - recent[0] >= self.window_seconds:
                recent.popleft()
            if len(recent) < self.rpm:
                recent.append(now)
                return
            wait = self.window_seconds - (now - recent[0])
            logger.debug("Rate limit: waiting %.1fs for %s", wait, key)
            self._sleep(max(wait, 0.01))

    def _load_daily_state(self) -> dict:
        # Re-read the file every time so several limiters in one process (or two
        # processes) don't overwrite each other's counts with stale numbers.
        today = self._today()
        state = self._memory_state
        if self.state_file is not None and self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Could not read %s; starting today's count from 0", self.state_file)
                state = {"date": None, "counts": {}}
        if state.get("date") != today:
            state = {"date": today, "counts": {}}
        return state

    def _save_daily_state(self, state: dict) -> None:
        self._memory_state = state
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_file)


def backoff_delay(
    attempt: int,
    base: float = 2.0,
    cap: float = 60.0,
    rng: Callable[[], float] = random.random,
) -> float:
    """Exponential backoff with jitter for retry number `attempt` (0-based).

    Returns a delay between half and all of min(cap, base * 2**attempt), so retries
    spread out instead of all firing at the same moment.
    """
    ceiling = min(cap, base * (2**attempt))
    return ceiling / 2 + rng() * ceiling / 2
