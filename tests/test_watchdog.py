import asyncio
import unittest

from pyherdr.presentation.watchdog import BackgroundTaskWatchdog, EventLoopWatchdog


class _Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class WatchdogTests(unittest.IsolatedAsyncioTestCase):
    def test_event_loop_watchdog_reports_synthetic_delay(self):
        clock = _Clock()
        watchdog = EventLoopWatchdog(interval=0.5, threshold=1.0, clock=clock)

        self.assertIsNone(watchdog.observe())
        clock.advance(0.5)
        self.assertIsNone(watchdog.observe())
        clock.advance(1.75)
        event = watchdog.observe()

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, "event_loop_delay")
        self.assertIn("UI event loop delayed by", event.message)
        self.assertIn("worker/thread", event.hint)

    async def test_background_task_watchdog_reports_slow_awaitable(self):
        clock = _Clock()
        watchdog = BackgroundTaskWatchdog(threshold=1.0, clock=clock)
        events = []

        async def work() -> str:
            clock.advance(1.25)
            await asyncio.sleep(0)
            return "done"

        result = await watchdog.watch("poll state", work(), events.append)

        self.assertEqual(result, "done")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "background_task_slow")
        self.assertIn("poll state", events[0].message)

    async def test_background_task_watchdog_ignores_fast_awaitable(self):
        clock = _Clock()
        watchdog = BackgroundTaskWatchdog(threshold=1.0, clock=clock)
        events = []

        async def work() -> str:
            clock.advance(0.25)
            await asyncio.sleep(0)
            return "done"

        result = await watchdog.watch("poll state", work(), events.append)

        self.assertEqual(result, "done")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
