import unittest

from pyherdr.runtime import keys


class KeyEncodingTests(unittest.TestCase):
    def test_named_keys_are_case_insensitive(self):
        self.assertEqual(keys.encode_key("Enter"), "\r")
        self.assertEqual(keys.encode_key("UP"), "\x1b[A")

    def test_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            keys.encode_key("dpad-left")

    def test_ctrl_chords(self):
        self.assertEqual(keys.encode_ctrl("c"), "\x03")
        self.assertEqual(keys.encode_ctrl("A"), "\x01")

    def test_encode_key_accepts_ctrl_chords(self):
        self.assertEqual(keys.encode_key("ctrl+c"), "\x03")
        self.assertEqual(keys.encode_key("Ctrl+A"), "\x01")

    def test_ctrl_rejects_non_letters(self):
        with self.assertRaises(ValueError):
            keys.encode_ctrl("ctrl")
        with self.assertRaises(ValueError):
            keys.encode_ctrl("1")

    def test_literal_text_is_unchanged(self):
        self.assertEqual(keys.encode_text("ls -la\n"), "ls -la\n")


if __name__ == "__main__":
    unittest.main()
