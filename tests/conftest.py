"""
Shared pytest configuration.

Must set environment BEFORE any backend import:
- GHOST_MEMORY_PATH: keep tests off the real memory store
- NVIDIA_API_KEY: backend.main fails fast without it
- GHOST_AUTH_PASSWORD: backend.main fails fast without it (M2)
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault(
    "GHOST_MEMORY_PATH",
    str(
        Path(tempfile.gettempdir())
        / "ghost-test-memory.json"
    ),
)

os.environ.setdefault(
    "NVIDIA_API_KEY",
    "test-key-not-real",
)

os.environ.setdefault(
    "GHOST_AUTH_PASSWORD",
    "ghost-test-password",
)

# Headroom for the suite: every auth_client fixture use
# performs one login, and the M1 no-count-limit test
# uploads 15 documents. Tests that verify rate limiting
# monkeypatch their own small values.
os.environ.setdefault(
    "GHOST_RATE_LIMIT_LOGIN_PER_MIN",
    "500",
)

os.environ.setdefault(
    "GHOST_RATE_LIMIT_UPLOAD_PER_MIN",
    "200",
)


@pytest.fixture
def auth_client():
    """
    A TestClient with a valid session token baked into
    its default headers — every request is authenticated.
    """

    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)

    response = client.post(
        "/api/auth/login",
        json={
            "password": os.environ["GHOST_AUTH_PASSWORD"],
        },
    )

    assert response.status_code == 200, (
        f"login failed in fixture: {response.text}"
    )

    client.headers.update(
        {
            "Authorization": (
                f"Bearer {response.json()['token']}"
            ),
        }
    )

    yield client
