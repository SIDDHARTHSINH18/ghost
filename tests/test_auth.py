"""
M2 tests: authentication, session lifecycle, and the
auth middleware boundary (threat T1).
"""

import os

from fastapi.testclient import TestClient

from backend.core.security import session_store
from backend.main import app


PASSWORD = os.environ["GHOST_AUTH_PASSWORD"]

# Unauthenticated client for public/boundary tests.
client = TestClient(app)


def login(
    password=None,
    use_client=None,
):
    return (use_client or client).post(
        "/api/auth/login",
        json={"password": password or PASSWORD},
    )


class TestLogin:

    def test_login_returns_bearer_token(self):
        response = login()

        assert response.status_code == 200

        body = response.json()

        assert body["token_type"] == "bearer"
        assert len(body["token"]) >= 32
        assert body["expires_at"] > 0

    def test_wrong_password_401(self):
        response = login(password="definitely-wrong")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid password."

    def test_empty_password_401(self):
        response = login(password="   ")

        assert response.status_code == 401

    def test_missing_body_422(self):
        response = client.post(
            "/api/auth/login",
            json={},
        )

        assert response.status_code == 422


class TestAuthMiddlewareBoundary:
    """
    The core T1 fix: unauthenticated access to any
    /api route must be rejected.
    """

    def test_memory_requires_token(self):
        response = client.get("/api/memory")

        assert response.status_code == 401

        assert response.headers.get(
            "WWW-Authenticate",
        ) == "Bearer"

    def test_documents_requires_token(self):
        response = client.get("/api/documents")

        assert response.status_code == 401

    def test_graph_requires_token(self):
        response = client.get("/api/graph")

        assert response.status_code == 401

    def test_chat_requires_token(self):
        response = client.post(
            "/api/chat",
            json={"message": "hello"},
        )

        assert response.status_code == 401

    def test_garbage_token_rejected(self):
        response = client.get(
            "/api/memory",
            headers={
                "Authorization": (
                    "Bearer not-a-real-token"
                ),
            },
        )

        assert response.status_code == 401

    def test_root_is_public(self):
        assert (
            client.get("/").status_code
            == 200
        )

    def test_health_is_public(self):
        response = client.get("/health")

        assert response.status_code == 200

        assert (
            response.json()["status"]
            == "ok"
        )


class TestSessionEndpoints:

    def test_session_info_with_valid_token(
        self,
        auth_client,
    ):
        response = auth_client.get(
            "/api/auth/session",
        )

        assert response.status_code == 200

        body = response.json()

        assert body["valid"] is True
        assert body["expires_at"] > 0

    def test_logout_revokes_session(
        self,
        auth_client,
    ):
        # Logout with the valid token...
        response = auth_client.delete(
            "/api/auth/session",
        )

        assert response.status_code == 200
        assert response.json()["revoked"] is True

        # ...the same token must no longer open the API.
        after = auth_client.get("/api/memory")

        assert after.status_code == 401

    def test_expired_session_rejected(
        self,
        auth_client,
        monkeypatch,
    ):
        import backend.core.security as security

        token = auth_client.headers[
            "Authorization"
        ][len("Bearer "):]

        # Force future sessions to expire instantly;
        # existing ones still work, so create then
        # expire by manipulating the store directly.
        monkeypatch.setattr(
            security,
            "get_session_ttl_seconds",
            lambda: -1,
        )

        expired = session_store.create()

        assert (
            session_store.get_valid(
                expired.token,
            )
            is None
        )

        # Control: the untouched token still validates.
        assert (
            session_store.get_valid(token)
            is not None
        )


class TestSessionStoreUnit:

    def test_revoke_unknown_token(self):
        assert (
            session_store.revoke(
                "no-such-token",
            )
            is False
        )

    def test_create_and_get_roundtrip(self):
        session = session_store.create()

        assert (
            session_store.get_valid(
                session.token,
            )
            is session
        )

    def test_logout_requires_auth(self):
        # DELETE /api/auth/session without a token is
        # itself protected — logout cannot be used to
        # probe arbitrary tokens.
        response = client.delete(
            "/api/auth/session",
        )

        assert response.status_code == 401
