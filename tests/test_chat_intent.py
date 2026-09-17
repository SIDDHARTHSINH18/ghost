"""
Tests for deterministic intent routing and page logic
in backend/api/chat.py — the parts the spec requires to
stay deterministic (never LLM-guessed).
"""

from backend.api.chat import (
    document_has_page,
    extract_requested_page,
    find_exact_page_chunks,
    get_chunk_page_range,
    is_whole_document_request,
    should_use_document,
)
from backend.core.document_processor import DocumentProcessor


class TestWholeDocumentIntent:

    def test_explicit_summary_phrases(self):
        assert is_whole_document_request(
            "Summarize this document"
        )

        assert is_whole_document_request(
            "give me a summary of the pdf"
        )

    def test_summary_plus_document_words(self):
        assert is_whole_document_request(
            "summarize everything"
        )

    def test_targeted_question_not_whole_document(self):
        # "explain" is intentionally excluded from the
        # whole-document heuristic.
        assert not is_whole_document_request(
            "explain the Bhakti movement from the PDF"
        )

    def test_plain_question_not_whole_document(self):
        assert not is_whole_document_request(
            "what is my project called?"
        )


class TestDocumentRouting:

    def test_page_request_routes_to_document(self):
        assert should_use_document(
            "what is on page 49?"
        )

    def test_document_reference_routes_to_document(self):
        assert should_use_document(
            "according to the uploaded pdf, who won?"
        )

    def test_project_question_stays_out_of_document_mode(self):
        # Regression: an uploaded history PDF hijacked
        # GHOST-project questions.
        assert not should_use_document(
            "what is my project called?"
        )


class TestPageExtraction:

    def test_page_number(self):
        assert extract_requested_page("page 49") == 49

    def test_abbreviations(self):
        assert extract_requested_page("pg. 12") == 12
        assert extract_requested_page("p. 7") == 7

    def test_no_page(self):
        assert extract_requested_page("hello there") is None

    def test_zero_and_negative_rejected(self):
        assert extract_requested_page("page 0") is None


class TestChunkPageRanges:

    def make_chunk(self, start, end):
        return {
            "chunk_id": 0,
            "text": "x",
            "start_page": start,
            "end_page": end,
        }

    def test_range_fallback_to_page(self):
        chunk = {"chunk_id": 0, "page": 5}

        assert get_chunk_page_range(chunk) == (5, 5)

    def test_invalid_values_return_none(self):
        chunk = {"start_page": "abc", "end_page": "def"}

        assert get_chunk_page_range(chunk) == (None, None)

    def test_find_exact_page_chunks(self):
        chunks = [
            self.make_chunk(1, 2),
            self.make_chunk(3, 5),
            self.make_chunk(6, 9),
        ]

        found = find_exact_page_chunks(chunks, 4)

        assert len(found) == 1
        assert found[0]["start_page"] == 3

    def test_document_has_page(self):
        document = {
            "pages": [{"page": 1}, {"page": 2}],
            "chunks": [],
        }

        assert document_has_page(document, 2)
        assert not document_has_page(document, 3)


class TestChunking:

    def test_chunk_count_and_overlap(self):
        processor = DocumentProcessor(
            chunk_size=100,
            chunk_overlap=20,
        )

        words = [f"w{i}" for i in range(250)]

        chunks = processor.chunk_text(
            " ".join(words),
        )

        # 250 words, 100 per chunk, 20 overlap
        # → starts at 0, 80, 160 → 3 chunks.
        assert len(chunks) == 3

        assert chunks[0]["start_word"] == 0
        assert chunks[1]["start_word"] == 80
        assert chunks[2]["start_word"] == 160

        # Consecutive chunks share the overlap window.
        assert (
            chunks[0]["end_word"]
            - chunks[1]["start_word"]
            == 20
        )

    def test_empty_text(self):
        assert (
            DocumentProcessor().chunk_text("")
            == []
        )
