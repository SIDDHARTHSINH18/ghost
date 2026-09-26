"""
First-run passphrase setup (packaged ENMA).

Flow: the desktop layer creates config.env with a bootstrap
credential + ENMA_SETUP_PENDING=1; the backend exposes
POST /api/auth/setup exactly once, letting the user choose a
permanent passphrase. Persistence across restarts is a
config-file property: the chosen passphrase is written back and
the pending marker removed.
"""

import os

import pytest

from fastapi.testclient import TestClient

from backend.main import app


BOOTSTRAP = "bootstrap-credential-not-permanent"
CHOSEN = "my-own-permanent-passphrase"
SHORT = "short"
WRONG = "not-my-passphrase"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def pending_config(tmp_path, monkeypatch):
    """A packaged first-run configuration in a private temp dir."""

    config = tmp_path / "config.env"
    config.write_text(
        "\n".join(
            [
                "# ENMA first-run configuration",
                f"GHOST_AUTH_PASSWORD={BOOTSTRAP}",
                "GEMINI_API_KEY=SYNTHETIC_PROVIDER_KEY_123",
                "ENMA_SETUP_PENDING=1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ENMA_CONFIG_PATH", str(config))
    monkeypatch.setenv("ENMA_SETUP_PENDING", "1")

    yield config


def _setup(client, passphrase=CHOSEN, confirm=None):
    return client.post(
        "/api/auth/setup",
        json={
            "passphrase": passphrase,
            "confirm": confirm or passphrase,
        },
    )


class TestFirstRunSetup:

    def test_setup_completes_and_returns_session(
        self, client, pending_config
    ):
        response = _setup(client)

        assert response.status_code == 200
        assert response.json().get("token")

    def test_login_with_chosen_passphrase_works(
        self, client, pending_config
    ):
        _setup(client)

        login = client.post(
            "/api/auth/login",
            json={"password": CHOSEN},
        )

        assert login.status_code == 200

    def test_bootstrap_credential_rejected_after_setup(
        self, client, pending_config
    ):
        _setup(client)

        login = client.post(
            "/api/auth/login",
            json={"password": BOOTSTRAP},
        )

        assert login.status_code == 401

    def test_wrong_passphrase_rejected(self, client, pending_config):
        _setup(client)

        login = client.post(
            "/api/auth/login",
            json={"password": WRONG},
        )

        assert login.status_code == 401

    def test_setup_cannot_run_twice(self, client, pending_config):
        _setup(client)

        second = _setup(client, passphrase="another-pass-1")

        assert second.status_code == 409

    def test_short_passphrase_rejected(self, client, pending_config):
        response = _setup(client, passphrase=SHORT)

        assert response.status_code == 400
        assert "8 characters" in response.json()["detail"]

    def test_mismatched_confirm_rejected(self, client, pending_config):
        response = _setup(
            client, passphrase=CHOSEN, confirm=CHOSEN + "-nope"
        )

        assert response.status_code == 400
        assert "do not match" in response.json()["detail"]

    def test_setup_closed_when_not_pending(self, client, monkeypatch):
        monkeypatch.delenv("ENMA_SETUP_PENDING", raising=False)

        response = _setup(client)

        assert response.status_code == 409

    def test_config_updated_marker_cleared_other_lines_kept(
        self, client, pending_config
    ):
        _setup(client)

        content = pending_config.read_text(encoding="utf-8")

        assert f"GHOST_AUTH_PASSWORD={CHOSEN}" in content
        assert "ENMA_SETUP_PENDING" not in content
        # Provider configuration preserved untouched.
        assert "GEMINI_API_KEY=SYNTHETIC_PROVIDER_KEY_123" in content
        # Bootstrap credential is gone from disk.
        assert BOOTSTRAP not in content

    def test_setup_response_never_contains_passphrase(
        self, client, pending_config
    ):
        response = _setup(client)

        assert CHOSEN not in response.text
        assert BOOTSTRAP not in response.text

    def test_persistence_across_process_restart(
        self, client, pending_config
    ):
        """
        Chosen passphrase survives a restart: a fresh
        interpreter reads only the persisted config file.
        """

        import subprocess
        import sys

        _setup(client)

        snippet = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{os.getcwd()}')\n"
            f"os.environ['ENMA_CONFIG_PATH'] = r'{pending_config}'\n"
            "os.environ.pop('ENMA_SETUP_PENDING', None)\n"
            "import backend.core.services\n"
            "from backend.core.security import get_auth_password\n"
            "print('PERSISTED:', "
            "get_auth_password() == 'my-own-permanent-passphrase')\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert "PERSISTED: True" in result.stdout, result.stdout
