from typing import List, Dict


class DocumentProcessor:

    def __init__(self, chunk_size=1500, chunk_overlap=200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> List[Dict]:

        if not text:
            return []

        words = text.split()

        chunks = []

        start = 0
        chunk_id = 0

        while start < len(words):

            end = min(
                start + self.chunk_size,
                len(words)
            )

            chunk_words = words[start:end]

            chunk_text = " ".join(chunk_words)

            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "start_word": start,
                "end_word": end,
                "start_page": None,
                "end_page": None
            })

            chunk_id += 1

            if end >= len(words):
                break

            start = end - self.chunk_overlap

        return chunks