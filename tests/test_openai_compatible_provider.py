"""
Regression tests for the NVIDIA OpenAI-compatible provider
request path: payload correctness (model, stream=False,
kwargs like max_tokens pass-through) and safe diagnostics
(timing logged on stall/timeout, no Authorization material
in logs). Network is fully mocked via httpx.MockTransport.
"""

import logging
import types

import httpx
import pytest

import backend.providers.openai_compatible as mod
from backend.providers.openai_compatible import OpenAICompatibleProvider


@pytest.fixture
def provider():
    return OpenAICompatibleProvider(
        name="nemotron",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key-not-a-secret",
    )


def install_mock_transport(monkeypatch, handler):
    """
    Replace httpx.AsyncClient in the provider module with one
    bound to a MockTransport, capturing whatever the provider
    actually puts on the wire.
    """

    captured = {}

    def handler_wrapper(request):
        captured["url"] = str(request.url)
        captured["json"] = request.read()
        captured["auth_header"] = request.headers.get("authorization")
        return handler(request)

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler_wrapper),
            **kwargs,
        )

    # Shim only the members the provider module touches, so the
    # real httpx.AsyncClient stays reachable for building mocks.
    monkeypatch.setattr(
        mod,
        "httpx",
        types.SimpleNamespace(
            AsyncClient=client_factory,
            Timeout=httpx.Timeout,
            HTTPError=httpx.HTTPError,
        ),
    )

    return captured


class TestGeneratePayload:

    def test_stream_false_model_and_kwargs_on_wire(
        self,
        provider,
        monkeypatch,
    ):
        captured = install_mock_transport(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "OK"}}
                    ]
                },
            ),
        )

        import asyncio

        result = asyncio.run(
            provider.generate(
                messages=[
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "Reply with OK."},
                ],
                model="nvidia/nemotron-3.5-lightning-30b-a3b",
                max_tokens=20,
            )
        )

        assert result == "OK"

        assert (
            captured["url"]
            == "https://integrate.api.nvidia.com/v1/chat/completions"
        )

        import json

        payload = json.loads(captured["json"])

        assert payload["stream"] is False

        assert (
            payload["model"]
            == "nvidia/nemotron-3.5-lightning-30b-a3b"
        )

        assert payload["max_tokens"] == 20

        assert payload["messages"][0]["role"] == "system"

        assert payload["messages"][-1]["role"] == "user"

        # The key must be sent, but only in the header.
        assert captured["auth_header"] == "Bearer test-key-not-a-secret"


class TestStallDiagnostics:

    def test_timeout_logged_with_timing_and_no_secret(
        self,
        provider,
        monkeypatch,
        caplog,
    ):
        def slow_handler(request):
            raise httpx.ReadTimeout(
                "server never returned headers",
                request=request,
            )

        install_mock_transport(monkeypatch, slow_handler)

        import asyncio

        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            with pytest.raises(httpx.ReadTimeout):
                asyncio.run(
                    provider.generate(
                        messages=[
                            {"role": "user", "content": "hi"}
                        ],
                        model="nvidia/nemotron-3.5-lightning-30b-a3b",
                        max_tokens=20,
                    )
                )

        text = "\n".join(
            record.getMessage() for record in caplog.records
        )

        # Request was announced...
        assert "NVIDIA request:" in text

        assert (
            "nvidia/nemotron-3.5-lightning-30b-a3b" in text
        )

        # ...the failure was reported with a type and elapsed time.
        assert "ReadTimeout" in text

        assert "elapsed=" in text

        # The key must never appear in any log record.
        assert "test-key-not-a-secret" not in text
