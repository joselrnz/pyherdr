import base64
import subprocess
import unittest

from pyherdr.clipboard import ClipboardResult, LocalClipboardBackend, copy_text, osc52_sequence


class FakeBackend:
    def __init__(self, name: str, ok: bool) -> None:
        self.name = name
        self.ok = ok
        self.calls: list[str] = []

    def copy(self, text: str) -> ClipboardResult:
        self.calls.append(text)
        return ClipboardResult(self.ok, self.name, "" if self.ok else "failed")


class ClipboardTests(unittest.TestCase):
    def test_osc52_sequence_encodes_text_with_bel_terminator(self) -> None:
        sequence = osc52_sequence("hello")
        payload = base64.b64encode(b"hello").decode("ascii")
        self.assertEqual(sequence, f"\x1b]52;c;{payload}\a")

    def test_copy_text_tries_fallback_after_failure(self) -> None:
        first = FakeBackend("first", False)
        second = FakeBackend("second", True)

        result = copy_text("payload", [first, second])

        self.assertTrue(result.ok)
        self.assertEqual(result.backend, "second")
        self.assertEqual(first.calls, ["payload"])
        self.assertEqual(second.calls, ["payload"])

    def test_copy_text_reports_last_failure_when_all_backends_fail(self) -> None:
        first = FakeBackend("first", False)
        second = FakeBackend("second", False)

        result = copy_text("payload", [first, second])

        self.assertFalse(result.ok)
        self.assertEqual(result.backend, "second")
        self.assertEqual(result.error, "failed")

    def test_local_clipboard_uses_windows_clip_command(self) -> None:
        calls: list[tuple[list[str], str]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((command, str(kwargs["input"])))
            return subprocess.CompletedProcess(command, 0, "", "")

        backend = LocalClipboardBackend(platform="nt", which=lambda command: command, runner=runner)

        result = backend.copy("payload")

        self.assertTrue(result.ok)
        self.assertEqual(calls, [(["clip.exe"], "payload")])

    def test_local_clipboard_uses_first_available_posix_command(self) -> None:
        calls: list[list[str]] = []

        def which(command: str) -> str | None:
            return command if command == "xclip" else None

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        backend = LocalClipboardBackend(platform="posix", which=which, runner=runner)

        result = backend.copy("payload")

        self.assertTrue(result.ok)
        self.assertEqual(calls, [["xclip", "-selection", "clipboard"]])

    def test_local_clipboard_reports_missing_command(self) -> None:
        backend = LocalClipboardBackend(platform="posix", which=lambda _command: None)

        result = backend.copy("payload")

        self.assertFalse(result.ok)
        self.assertEqual(result.backend, "local")
        self.assertIn("no local clipboard command", result.error)


if __name__ == "__main__":
    unittest.main()
