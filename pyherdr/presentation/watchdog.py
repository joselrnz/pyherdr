from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar


@dataclass(frozen=True)
class WatchdogEvent:
    """Actionable diagnostic emitted when UI work blocks too long."""

    kind: str
    name: str
    elapsed_seconds: float
    threshold_seconds: float
    message: str
    hint: str


class EventLoopWatchdog:
    """Detect event-loop starvation by measuring sleep drift."""

    def __init__(
        self,
        *,
        interval: float = 0.5,
        threshold: float = 1.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval = interval
        self.threshold = threshold
        self._clock = clock
        self._last: float | None = None

    def observe(self) -> WatchdogEvent | None:
        now = self._clock()
        if self._last is None:
            self._last = now
            return None
        expected = self._last + self.interval
        self._last = now
        delay = now - expected
        if delay < self.threshold:
            return None
        return WatchdogEvent(
            kind="event_loop_delay",
            name="textual event loop",
            elapsed_seconds=delay,
            threshold_seconds=self.threshold,
            message=f"UI event loop delayed by {delay:.2f}s",
            hint="Move blocking UI work into a worker/thread or reduce synchronous render work.",
        )

    async def run(self, report: Callable[[WatchdogEvent], None]) -> None:
        while True:
            await asyncio.sleep(self.interval)
            event = self.observe()
            if event is not None:
                report(event)


T = TypeVar("T")


class BackgroundTaskWatchdog:
    """Report slow background worker steps after they complete."""

    def __init__(
        self,
        *,
        threshold: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self._clock = clock

    def start(self) -> float:
        return self._clock()

    def finish(self, name: str, started_at: float) -> WatchdogEvent | None:
        elapsed = self._clock() - started_at
        if elapsed < self.threshold:
            return None
        return WatchdogEvent(
            kind="background_task_slow",
            name=name,
            elapsed_seconds=elapsed,
            threshold_seconds=self.threshold,
            message=f"Background task '{name}' took {elapsed:.2f}s",
            hint="Check server I/O, process sampling, or filesystem work for blocking calls.",
        )

    async def watch(self, name: str, awaitable: Awaitable[T], report: Callable[[WatchdogEvent], None]) -> T:
        started_at = self.start()
        try:
            return await awaitable
        finally:
            event = self.finish(name, started_at)
            if event is not None:
                report(event)
