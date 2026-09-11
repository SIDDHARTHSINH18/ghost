from typing import List, Dict


class ContextOptimizer:

    def __init__(self, max_words=4500):
        self.max_words = max_words

    def optimize(
        self,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not chunks:
            return []

        # Remove duplicate chunks
        unique_chunks = {}

        for chunk in chunks:

            chunk_id = chunk.get("chunk_id")

            if chunk_id not in unique_chunks:
                unique_chunks[chunk_id] = chunk

        chunks = list(
            unique_chunks.values()
        )

        # Separate strong matches from neighboring context
        primary_chunks = [
            chunk
            for chunk in chunks
            if not chunk.get("is_neighbor", False)
        ]

        neighbor_chunks = [
            chunk
            for chunk in chunks
            if chunk.get("is_neighbor", False)
        ]

        # Strongest matches first
        primary_chunks.sort(
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        selected_chunks = []
        selected_ids = set()
        total_words = 0

        # First add the most relevant chunks
        for chunk in primary_chunks:

            chunk_words = len(
                chunk["text"].split()
            )

            if (
                total_words + chunk_words
                > self.max_words
            ):
                continue

            selected_chunks.append(chunk)

            selected_ids.add(
                chunk["chunk_id"]
            )

            total_words += chunk_words

        # Then add neighboring context if space remains
        for chunk in neighbor_chunks:

            if chunk["chunk_id"] in selected_ids:
                continue

            chunk_words = len(
                chunk["text"].split()
            )

            if (
                total_words + chunk_words
                > self.max_words
            ):
                continue

            selected_chunks.append(chunk)

            selected_ids.add(
                chunk["chunk_id"]
            )

            total_words += chunk_words

        # Return context in original document order
        selected_chunks.sort(
            key=lambda x: x.get(
                "chunk_id",
                0
            )
        )

        return selected_chunks

    def build_context(
        self,
        chunks: List[Dict]
    ) -> str:

        optimized_chunks = self.optimize(
            chunks
        )

        context_parts = []

        for chunk in optimized_chunks:

            context_parts.append(
                chunk["text"]
            )

        return "\n\n".join(
            context_parts
        )