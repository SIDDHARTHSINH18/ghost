"""
Tests for the context optimizer's word budget,
deduplication, and neighbor handling.
"""

from backend.core.context_optimizer import ContextOptimizer


def make_chunk(chunk_id, word_count, score=1.0, neighbor=False):
    return {
        "chunk_id": chunk_id,
        "text": " ".join(
            f"w{i}" for i in range(word_count)
        ),
        "score": score,
        "is_neighbor": neighbor,
    }


class TestOptimize:

    def test_budget_respected(self):
        optimizer = ContextOptimizer(max_words=150)

        chunks = [
            make_chunk(0, 100),
            make_chunk(1, 100),
        ]

        selected = optimizer.optimize(chunks)

        total_words = sum(
            len(c["text"].split())
            for c in selected
        )

        assert total_words <= 150
        assert len(selected) == 1

    def test_stronger_score_kept_within_budget(self):
        optimizer = ContextOptimizer(max_words=150)

        chunks = [
            make_chunk(0, 100, score=0.2),
            make_chunk(1, 100, score=0.9),
        ]

        selected = optimizer.optimize(chunks)

        assert [c["chunk_id"] for c in selected] == [1]

    def test_duplicates_removed(self):
        optimizer = ContextOptimizer(max_words=500)

        chunks = [
            make_chunk(0, 50),
            make_chunk(0, 50),
        ]

        selected = optimizer.optimize(chunks)

        assert len(selected) == 1

    def test_neighbors_only_added_if_space(self):
        optimizer = ContextOptimizer(max_words=120)

        chunks = [
            make_chunk(0, 100),
            make_chunk(1, 100, neighbor=True),
        ]

        selected = optimizer.optimize(chunks)

        assert [c["chunk_id"] for c in selected] == [0]

    def test_output_in_document_order(self):
        optimizer = ContextOptimizer(max_words=1000)

        chunks = [
            make_chunk(2, 10, score=0.9),
            make_chunk(0, 10, score=0.8),
            make_chunk(1, 10, score=0.7),
        ]

        selected = optimizer.optimize(chunks)

        assert [c["chunk_id"] for c in selected] == [0, 1, 2]


class TestBuildContext:

    def test_joins_with_blank_lines(self):
        optimizer = ContextOptimizer(max_words=100)

        chunks = [
            make_chunk(0, 2),
            make_chunk(1, 2),
        ]

        context = optimizer.build_context(chunks)

        assert context.count("\n\n") == 1

    def test_empty(self):
        assert (
            ContextOptimizer().build_context([])
            == ""
        )
