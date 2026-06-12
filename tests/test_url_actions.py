import unittest

from pyherdr.url_actions import extract_urls


class UrlActionTests(unittest.TestCase):
    def test_extract_urls_deduplicates_and_trims_terminal_punctuation(self):
        text = (
            "Preview: https://localhost:3000/app.\n"
            "Docs: https://example.com/path?q=1) and http://127.0.0.1:8000/logs\n"
            "Again https://localhost:3000/app"
        )

        self.assertEqual(
            extract_urls(text),
            [
                "https://localhost:3000/app",
                "https://example.com/path?q=1",
                "http://127.0.0.1:8000/logs",
            ],
        )


if __name__ == "__main__":
    unittest.main()
