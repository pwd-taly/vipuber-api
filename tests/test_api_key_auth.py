import asyncio
import os
import unittest

os.environ.setdefault("VIPUBER_EMAIL", "test@example.com")
os.environ.setdefault("VIPUBER_PASSWORD", "test")
os.environ["API_KEY"] = "test-key"

from main import app  # noqa: E402


async def call_app(path: str, headers: dict[str, str] | None = None):
    messages = []
    header_items = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": header_items,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status, body


class ApiKeyAuthTests(unittest.TestCase):
    def test_health_is_public(self):
        status, _ = asyncio.run(call_app("/health"))
        self.assertEqual(status, 200)

    def test_protected_route_rejects_missing_key(self):
        status, body = asyncio.run(call_app("/locations"))
        self.assertEqual(status, 401)
        self.assertIn(b"Invalid or missing X-API-Key", body)

    def test_protected_route_rejects_wrong_key(self):
        status, body = asyncio.run(call_app("/locations", {"X-API-Key": "wrong"}))
        self.assertEqual(status, 401)
        self.assertIn(b"Invalid or missing X-API-Key", body)

    def test_correct_key_passes_auth_middleware(self):
        status, _ = asyncio.run(call_app("/definitely-missing", {"X-API-Key": "test-key"}))
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
