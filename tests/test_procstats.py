import unittest
from types import SimpleNamespace
from typing import Any

import pyherdr.runtime.procstats as procstats


class _FakeProc:
    def __init__(
        self,
        pid: int,
        *,
        children: list["_FakeProc"] | None = None,
        children_error: Exception | None = None,
        read_error: Exception | None = None,
    ) -> None:
        self.pid = pid
        self._children = children or []
        self._children_error = children_error
        self._read_error = read_error

    def cpu_percent(self, _interval: object = None) -> float:
        if self._read_error is not None:
            raise self._read_error
        return float(self.pid)

    def memory_info(self) -> SimpleNamespace:
        if self._read_error is not None:
            raise self._read_error
        return SimpleNamespace(rss=self.pid * 1024)

    def name(self) -> str:
        if self._read_error is not None:
            raise self._read_error
        return f"proc-{self.pid}"

    def cmdline(self) -> list[str]:
        if self._read_error is not None:
            raise self._read_error
        return [f"cmd-{self.pid}"]

    def children(self, recursive: bool = False) -> list["_FakeProc"]:
        if self._children_error is not None:
            raise self._children_error
        return self._children


class _FakePsutil:
    def __init__(self, procs: dict[int, _FakeProc], error_pids: set[int] | None = None) -> None:
        self._procs = procs
        self._error_pids = error_pids or set()

    def Process(self, pid: int) -> _FakeProc:
        if pid in self._error_pids:
            raise PermissionError("denied")
        return self._procs[pid]


class ProcStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._available = procstats.AVAILABLE
        self._ps: Any = procstats._PS

    def tearDown(self) -> None:
        procstats.AVAILABLE = self._available
        procstats._PS = self._ps

    def test_sample_records_unavailable_process_instead_of_dropping_pane(self):
        procstats.AVAILABLE = True
        procstats._PS = _FakePsutil({}, error_pids={100})
        sampler = procstats.ProcSampler()

        sampler.sample({"pane-1": 100})
        stat = sampler.snapshot()["pane-1"]

        self.assertEqual(stat["pid"], 100)
        self.assertEqual(stat["num_procs"], 0)
        self.assertIn("permission denied", stat["error"])

    def test_sample_warns_when_children_cannot_be_inspected(self):
        root = _FakeProc(10, children_error=PermissionError("children denied"))
        procstats.AVAILABLE = True
        procstats._PS = _FakePsutil({10: root})
        sampler = procstats.ProcSampler()

        sampler.sample({"pane-1": 10})
        stat = sampler.snapshot()["pane-1"]

        self.assertEqual(stat["num_procs"], 1)
        self.assertEqual(stat["procs"][0]["cmd"], "cmd-10")
        self.assertIn("could not inspect child processes: PermissionError", stat["warnings"])

    def test_sample_warns_when_some_processes_cannot_be_read(self):
        child = _FakeProc(11, read_error=PermissionError("child denied"))
        root = _FakeProc(10, children=[child])
        procstats.AVAILABLE = True
        procstats._PS = _FakePsutil({10: root, 11: child})
        sampler = procstats.ProcSampler()

        sampler.sample({"pane-1": 10})
        stat = sampler.snapshot()["pane-1"]

        self.assertEqual(stat["num_procs"], 1)
        self.assertIn("1 process(es) could not be inspected", stat["warnings"])

    def test_sample_without_psutil_clears_snapshot(self):
        procstats.AVAILABLE = False
        sampler = procstats.ProcSampler()
        sampler._snapshot = {"pane-1": {"pid": 10}}

        sampler.sample({"pane-1": 10})

        self.assertEqual(sampler.snapshot(), {})


if __name__ == "__main__":
    unittest.main()
