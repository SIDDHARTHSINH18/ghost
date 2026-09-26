"""
Focused regression tests for:

1. /health/provider using the canonical health_check()
   interface with the Gemini provider (no ping() call),
   and reporting the actual active provider.
2. Chat/provider exception text being scrubbed through
   the shared redact_text() before it reaches logs —
   provider errors can carry API-key URLs such as
   "...?key=SYNTHETIC_GOOGLE_TEST_KEY".

No network calls: provider methods are replaced with
capturing fakes.
"""

import json
import logging
import os

from fastapi.testclient import TestClient

from backend.core.services import orchestrator
from backend.main import app


client = TestClient(app)


def auth_headers():
    response = client.post(
        "/api/auth/login",
        json={
            "password": os.environ[
                "GHOST_AUTH_PASSWORD"
            ],
        },
    )

    assert response.status_code == 200

    token = (
        response.json().get("session_token")
        or response.json().get("token")
    )

    return {"Authorization": f"Bearer {token}"}


class TestProviderHealthEndpoint:

    def test_health_provider_uses_health_check_with_gemini(
        self,
        monkeypatch,
    ):
        """
        The endpoint must call the canonical
        health_check() (GeminiProvider has no ping())
        and identify the active provider as gemini.
        """

        gemini = orchestrator.get_provider("gemini")

        calls = {"count": 0}

        async def fake_health_check():
            calls["count"] += 1

            return True

        monkeypatch.setattr(
            gemini,
            "health_check",
            fake_health_check,
        )

        response = client.get(
            "/health/provider",
            headers=auth_headers(),
        )

        assert response.status_code == 200

        body = response.json()

        assert calls["count"] == 1

        # The actual active/default provider.
        assert body["provider"] == "gemini"

        assert body["online"] is True
        assert body["reachable"] is True

        assert body["model"]

    def test_health_provider_reports_unreachable(
        self,
        monkeypatch,
    ):
        gemini = orchestrator.get_provider("gemini")

        async def failing_health_check():
            raise RuntimeError("network down")

        monkeypatch.setattr(
            gemini,
            "health_check",
            failing_health_check,
        )

        response = client.get(
            "/health/provider",
            headers=auth_headers(),
        )

        # A failed health probe is a 200 with
        # online=false, not an AttributeError/500.
        assert response.status_code == 200

        body = response.json()

        assert body["provider"] == "gemini"
        assert body["online"] is False


class TestChatProviderErrorRedaction:

    SYNTHETIC_KEY_URL = (
        "https://generativelanguage.googleapis.com"
        "/v1beta/models/gemini-3.5-flash"
        ":streamGenerateContent"
        "?key=SYNTHETIC_GOOGLE_TEST_KEY"
    )

    def test_provider_error_url_key_is_redacted(
        self,
        monkeypatch,
        caplog,
    ):
        async def failing_generate_stream(
            messages,
            model=None,
            **kwargs,
        ):
            raise RuntimeError(
                "request failed for "
                f"{self.SYNTHETIC_KEY_URL}"
            )

            yield ""  # pragma: no cover

        for provider in orchestrator.providers.values():
            monkeypatch.setattr(
                provider,
                "generate_stream",
                failing_generate_stream,
            )

        with caplog.at_level(
            logging.ERROR,
            logger="ghost.chat",
        ):

            with client.stream(
                "POST",
                "/api/chat",
                json={
                    "message": "hello",
                    "provider": "gemini",
                    "model": None,
                    "document_id": None,
                    "history": [],
                },
                headers=auth_headers(),
            ) as response:

                assert response.status_code == 200

                text = "".join(
                    response.iter_text()
                )

        # Client sees the generic failure text, never
        # the exception or the key.
        assert "SYNTHETIC_GOOGLE_TEST_KEY" not in text

        assert "could not complete" in text

        # Server logs carry the error, scrubbed.
        logged = json.dumps(
            [record.getMessage() for record in caplog.records]
        )

        assert "Chat generation failed" in logged

        assert (
            "SYNTHETIC_GOOGLE_TEST_KEY" not in logged
        )

        assert "[redacted]" in logged


class TestProviderHealthReason:

    def _patch(self, monkeypatch, status_code=None):
        gemini = orchestrator.get_provider("gemini")

        async def fake_health_check():
            gemini.last_health_status_code = status_code
            gemini.last_health_error_type = None
            return status_code is not None and status_code < 400

        monkeypatch.setattr(gemini, "health_check", fake_health_check)

    def test_healthy_reports_ok_reason(self, monkeypatch):
        self._patch(monkeypatch, 200)

        body = client.get(
            "/health/provider", headers=auth_headers()
        ).json()

        assert body["reason"] == "ok"
        assert body["online"] is True
        assert body["provider"] == "gemini"

    def test_rate_limited_reason(self, monkeypatch):
        self._patch(monkeypatch, 429)

        body = client.get(
            "/health/provider", headers=auth_headers()
        ).json()

        assert body["reason"] == "rate_limited"
        assert body["status_code"] == 429
        assert body["online"] is False

    def test_unavailable_reason(self, monkeypatch):
        self._patch(monkeypatch, 503)

        body = client.get(
            "/health/provider", headers=auth_headers()
        ).json()

        assert body["reason"] == "unavailable"
        assert body["status_code"] == 503

    def test_other_error_reason(self, monkeypatch):
        self._patch(monkeypatch, 500)

        body = client.get(
            "/health/provider", headers=auth_headers()
        ).json()

        assert body["reason"] == "error"
