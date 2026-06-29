import os
import unittest

os.environ.setdefault("VIPUBER_EMAIL", "test@example.com")
os.environ.setdefault("VIPUBER_PASSWORD", "default-password")
os.environ.setdefault("API_KEY", "test-key")

from session import _sessions, get_session


class SessionCacheTests(unittest.TestCase):
    def setUp(self):
        _sessions.clear()

    def test_same_email_with_new_password_creates_fresh_session(self):
        first = get_session("driver@example.com", "wrong-password")
        second = get_session("driver@example.com", "correct-password")

        self.assertIsNot(first, second)
        self.assertEqual(second.password, "correct-password")

    def test_email_is_normalized_for_cache_key(self):
        first = get_session(" Driver@Example.com ", "same-password")
        second = get_session("driver@example.com", "same-password")

        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
