"""
M2 tests: rate limiting — unit behavior of the
sliding window plus API-level 429s with Retry-After.
"""

import time

from backend.core.security import RateLimiter


class TestRateLimiterUnit:

    def test_allows_up_to_limit(self):
        limiter = RateLimiter()

        for _ in range(3):
            allowed, _ = limiter.check(
                "key",
                limit=3,
            )

            assert allowed is True

    def test_blocks_beyond_limit_with_retry_after(self):
        limiter = RateLimiter()

        for _ in range(2):
            limiter.check("key", limit=2)

        allowed, retry_after = limiter.check(
            "key",
            limit=2,
        )

        assert allowed is False
        assert retry_after >= 1

    def test_window_slides(self):
        limiter = RateLimiter()

        for _ in range(2):
            limiter.check("key", limit=2)

        assert limiter.check("key", limit=2)[0] is False

        # After the window passes the counter resets.
        time.sleep(0.3)

        allowed, _ = limiter.check(
            "key",
            limit=2,
            window_seconds=0.2,
        )

        assert allowed is True

    def test_keys_are_independent(self):
        limiter = RateLimiter()

        for _ in range(2):
            limiter.check("a", limit=2)

        assert limiter.check("b", limit=2)[0] is True


class TestChatRateLimitAPI:
    """
    Uses a nonexistent provider so requests fail at the
    provider lookup — rate events are consumed but no
    network call is ever made.
    """

    def test_third_request_429(
        self,
        auth_client,
        monkeypatch,
    ):
        monkeypatch.setenv(
            "GHOST_RATE_LIMIT_CHAT_PER_MIN",
            "2",
        )

        body = {
            "message": "hello there friend",
            "provider": "does-not-exist",
        }

        first = auth_client.post(
            "/api/chat",
            json=body,
        )

        second = auth_client.post(
            "/api/chat",
            json=body,
        )

        third = auth_client.post(
            "/api/chat",
            json=body,
        )

        # The first two pass the rate limit and fail at
        # provider lookup (404) instead.
        assert first.status_code == 404
        assert second.status_code == 404

        # The third is stopped by the rate limit.
        assert third.status_code == 429
        assert "Retry-After" in third.headers


class TestUploadRateLimitAPI:

    def test_second_upload_429(
        self,
        auth_client,
        monkeypatch,
    ):
        monkeypatch.setenv(
            "GHOST_RATE_LIMIT_UPLOAD_PER_MIN",
            "1",
        )

        import io

        first = auth_client.post(
            "/api/upload",
            files={
                "file": (
                    "one.txt",
                    io.BytesIO(
                        b"first document content",
                    ),
                    "text/plain",
                ),
            },
        )

        second = auth_client.post(
            "/api/upload",
            files={
                "file": (
                    "two.txt",
                    io.BytesIO(
                        b"second document content",
                    ),
                    "text/plain",
                ),
            },
        )

        assert first.status_code == 200

        assert second.status_code == 429
        assert "Retry-After" in second.headers


class TestLoginBruteForce:

    def test_rapid_failures_get_throttled(
        self,
        monkeypatch,
    ):
        from fastapi.testclient import TestClient

        from backend.main import app

        monkeypatch.setenv(
            "GHOST_RATE_LIMIT_LOGIN_PER_MIN",
            "2",
        )

        client = TestClient(app)

        statuses = []

        for _ in range(6):

            response = client.post(
                "/api/auth/login",
                json={
                    "password": "wrong guess",
                },
            )

            statuses.append(
                response.status_code,
            )

        # Never a success; brute force is slowed by 429s.
        assert 200 not in statuses
        assert 429 in statuses

        throttled = [
            r
            for r in [
                client.post(
                    "/api/auth/login",
                    json={
                        "password": "wrong guess",
                    },
                )
            ]
            if r.status_code == 429
        ]

        if throttled:

            assert "Retry-After" in (
                throttled[0].headers
            )
