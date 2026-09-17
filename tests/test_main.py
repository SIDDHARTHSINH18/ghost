"""
API shell tests: health, validation, routing errors.
No network calls — every tested path fails before
the provider is contacted.
"""

import io

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


class TestHealth:

    def test_health_ok(self):
        response = client.get("/health")

        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "ok"

        assert (
            body["provider"]["api_key_present"]
            is True
        )

    def test_root(self):
        response = client.get("/")

        assert response.status_code == 200


class TestChatValidation:

    def test_empty_message_rejected(self):
        response = client.post(
            "/api/chat",
            json={"message": "   "},
        )

        assert response.status_code == 400

    def test_unknown_provider_rejected(self):
        response = client.post(
            "/api/chat",
            json={
                "message": "hello there",
                "provider": "does-not-exist",
            },
        )

        assert response.status_code == 404

    def test_missing_document_rejected(self):
        response = client.post(
            "/api/chat",
            json={
                "message": "what is on page 5?",
                "document_id": "no-such-document",
            },
        )

        assert response.status_code == 404


class TestUploadValidation:

    def test_unsupported_file_type(self):
        response = client.post(
            "/api/upload",
            files={
                "file": (
                    "malware.exe",
                    io.BytesIO(b"MZ..."),
                    "application/x-msdownload",
                ),
            },
        )

        assert response.status_code == 400

    def test_empty_text_file_rejected(self):
        response = client.post(
            "/api/upload",
            files={
                "file": (
                    "empty.txt",
                    io.BytesIO(b"   "),
                    "text/plain",
                ),
            },
        )

        assert response.status_code == 400


class TestGraph:

    def test_graph_memory_labels_not_content(self):
        from backend.core.services import memory_service

        memory_service.add_memory(
            content="GRAPHTEST secret personal fact alpha",
        )

        response = client.get("/api/graph")

        assert response.status_code == 200

        text = response.text

        # Privacy: content must not leak through the
        # graph endpoint — labels only.
        assert "secret personal fact alpha" not in text

        assert '"memories"' in text
