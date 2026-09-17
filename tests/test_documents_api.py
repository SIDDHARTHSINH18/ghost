"""
M1 API tests: document listing, deletion, upload
validation, and configurable limits.

Explicitly includes a no-arbitrary-count-limit test:
many documents must upload successfully while real
resource limits (file size, total storage) still apply.
"""

import io

import pytest

from fastapi.testclient import TestClient

from backend.core.config import get_upload_limits
from backend.core.services import documents
from backend.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_documents():
    documents.clear()
    yield
    documents.clear()


def upload_txt(
    name: str,
    text: str,
):
    return client.post(
        "/api/upload",
        files={
            "file": (
                name,
                io.BytesIO(text.encode("utf-8")),
                "text/plain",
            ),
        },
    )


class TestDocumentListing:

    def test_upload_then_list_metadata(self):
        response = upload_txt(
            "notes.txt",
            "alpha beta gamma delta epsilon",
        )

        assert response.status_code == 200

        document_id = response.json()["document_id"]

        listing = client.get("/api/documents")

        assert listing.status_code == 200

        body = listing.json()

        assert body["total"] == 1

        item = body["documents"][0]

        # Safe metadata required by M1 scope.
        assert (
            item["document_id"] == document_id
        )
        assert item["filename"] == "notes.txt"
        assert item["pages"] >= 1
        assert item["chunks"] >= 1
        assert item["status"] == "indexed"
        assert item["has_summary"] is False

        # Privacy: document body text must never
        # appear in the listing.
        assert (
            "alpha beta gamma delta epsilon"
            not in listing.text
        )

    def test_empty_listing(self):
        body = client.get("/api/documents").json()

        assert body == {
            "documents": [],
            "total": 0,
            "total_size_bytes": 0,
        }


class TestDocumentDeletion:

    def test_delete_verifies_store_is_clean(self):
        created = upload_txt(
            "gone.txt",
            "some meaningful content for deletion test",
        )

        document_id = created.json()["document_id"]

        response = client.delete(
            f"/api/documents/{document_id}",
        )

        assert response.status_code == 200

        body = response.json()

        assert body["deleted"] is True
        assert body["verified"] is True

        # Gone from the listing...
        listing = client.get("/api/documents").json()

        assert listing["total"] == 0

        # ...and gone from the active store: chat with
        # the deleted id must 404.
        chat = client.post(
            "/api/chat",
            json={
                "message": "what is on page 5?",
                "document_id": document_id,
            },
        )

        assert chat.status_code == 404

    def test_delete_unknown_document_404(self):
        response = client.delete(
            "/api/documents/no-such-id",
        )

        assert response.status_code == 404


class TestUploadValidation:

    def test_unsupported_extension_400(self):
        response = client.post(
            "/api/upload",
            files={
                "file": (
                    "evil.exe",
                    io.BytesIO(b"MZ"),
                    "application/x-msdownload",
                ),
            },
        )

        assert response.status_code == 400
        assert "Unsupported file type" in (
            response.json()["detail"]
        )

    def test_extension_list_configurable(self, monkeypatch):
        monkeypatch.setenv(
            "GHOST_ALLOWED_EXTENSIONS",
            ".txt",
        )

        limits = get_upload_limits()

        assert limits.allowed_extensions == (".txt",)

        # .pdf now rejected by configuration.
        pdf_response = client.post(
            "/api/upload",
            files={
                "file": (
                    "doc.pdf",
                    __import__("io").BytesIO(
                        b"%PDF-1.4 fake"
                    ),
                    "application/pdf",
                ),
            },
        )

        assert pdf_response.status_code == 400

    def test_no_readable_text_400(self):
        response = upload_txt(
            "blank.txt",
            "   ",
        )

        assert response.status_code == 400
        assert "no readable text" in (
            response.json()["detail"]
        )


class TestConfigurableLimits:

    def test_per_file_size_limit_413(self, monkeypatch):
        monkeypatch.setenv(
            "GHOST_MAX_UPLOAD_MB",
            "0",
        )

        response = upload_txt(
            "tiny.txt",
            "still too big for a zero limit",
        )

        assert response.status_code == 413
        assert "GHOST_MAX_UPLOAD_MB" in (
            response.json()["detail"]
        )

    def test_total_storage_limit_413(self, monkeypatch):
        monkeypatch.setenv(
            "GHOST_MAX_TOTAL_STORAGE_MB",
            "0",
        )

        response = upload_txt(
            "tiny.txt",
            "content",
        )

        assert response.status_code == 413
        assert (
            "GHOST_MAX_TOTAL_STORAGE_MB"
            in response.json()["detail"]
        )

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(
            "GHOST_MAX_UPLOAD_MB",
            "not-a-number",
        )

        limits = get_upload_limits()

        assert (
            limits.max_upload_bytes
            == 50 * 1024 * 1024
        )


class TestNoDocumentCountLimit:

    def test_many_documents_all_upload(self):
        """
        The old design risk was an arbitrary "maximum N
        documents" rule. Fifteen documents (well above
        any such guess) must all upload under default
        resource limits.
        """

        for index in range(15):

            response = upload_txt(
                f"doc{index}.txt",
                f"document number {index} with content",
            )

            assert response.status_code == 200, (
                f"upload {index} failed: "
                f"{response.text}"
            )

        listing = client.get("/api/documents").json()

        assert listing["total"] == 15
