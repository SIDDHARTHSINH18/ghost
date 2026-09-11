import re
from typing import List, Dict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sentence_transformers import SentenceTransformer


class DocumentRetriever:

    def __init__(
        self,
        top_k=5,
        neighbor_chunks=1,
        semantic_weight=0.60,
        tfidf_weight=0.25,
        keyword_weight=0.10,
        phrase_weight=0.05
    ):
        self.top_k = top_k
        self.neighbor_chunks = neighbor_chunks

        self.semantic_weight = semantic_weight
        self.tfidf_weight = tfidf_weight
        self.keyword_weight = keyword_weight
        self.phrase_weight = phrase_weight

        self.embedding_model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

    def _tokenize(self, text: str) -> set:
        return set(
            re.findall(
                r"\b[a-zA-Z0-9]+\b",
                text.lower()
            )
        )

    def _keyword_score(
        self,
        query: str,
        chunk_text: str
    ) -> float:

        query_words = self._tokenize(query)
        chunk_words = self._tokenize(chunk_text)

        if not query_words or not chunk_words:
            return 0.0

        matches = query_words.intersection(chunk_words)

        return len(matches) / len(query_words)

    def _phrase_score(
        self,
        query: str,
        chunk_text: str
    ) -> float:

        query_clean = " ".join(query.lower().split())
        chunk_clean = " ".join(chunk_text.lower().split())

        if not query_clean:
            return 0.0

        if query_clean in chunk_clean:
            return 1.0

        query_words = query_clean.split()

        if len(query_words) < 2:
            return 0.0

        matched_pairs = 0
        total_pairs = len(query_words) - 1

        for index in range(total_pairs):

            phrase = (
                query_words[index]
                + " "
                + query_words[index + 1]
            )

            if phrase in chunk_clean:
                matched_pairs += 1

        return matched_pairs / total_pairs

    def create_embeddings(
        self,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not chunks:
            return []

        texts = [
            chunk["text"]
            for chunk in chunks
        ]

        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        updated_chunks = []

        for index, chunk in enumerate(chunks):

            updated_chunk = {
                **chunk,
                "embedding": embeddings[index].tolist()
            }

            updated_chunks.append(updated_chunk)

        return updated_chunks

    def _semantic_scores(
        self,
        query: str,
        chunks: List[Dict]
    ) -> List[float]:

        if not chunks:
            return []

        try:

            query_embedding = self.embedding_model.encode(
                [query],
                normalize_embeddings=True,
                show_progress_bar=False
            )

            document_embeddings = [
                chunk["embedding"]
                for chunk in chunks
                if "embedding" in chunk
            ]

            if len(document_embeddings) != len(chunks):
                return [0.0 for _ in chunks]

            scores = cosine_similarity(
                query_embedding,
                document_embeddings
            )[0]

            return [
                float(score)
                for score in scores
            ]

        except Exception as error:

            print(
                f"Semantic retrieval error: {error}"
            )

            return [
                0.0
                for _ in chunks
            ]

    def retrieve(
        self,
        query: str,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not query or not chunks:
            return []

        texts = [
            chunk["text"]
            for chunk in chunks
        ]

        try:

            vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 2),
                sublinear_tf=True
            )

            document_vectors = vectorizer.fit_transform(
                texts
            )

            query_vector = vectorizer.transform(
                [query]
            )

            tfidf_scores = cosine_similarity(
                query_vector,
                document_vectors
            )[0]

        except ValueError:

            tfidf_scores = [
                0.0
                for _ in chunks
            ]

        semantic_scores = self._semantic_scores(
            query,
            chunks
        )

        scored_chunks = []

        for index, chunk in enumerate(chunks):

            keyword_score = self._keyword_score(
                query,
                chunk["text"]
            )

            phrase_score = self._phrase_score(
                query,
                chunk["text"]
            )

            tfidf_score = float(
                tfidf_scores[index]
            )

            semantic_score = float(
                semantic_scores[index]
            )

            final_score = (
                (semantic_score * self.semantic_weight)
                + (tfidf_score * self.tfidf_weight)
                + (keyword_score * self.keyword_weight)
                + (phrase_score * self.phrase_weight)
            )

            scored_chunks.append({
                **chunk,
                "score": final_score,
                "semantic_score": semantic_score,
                "tfidf_score": tfidf_score,
                "keyword_score": keyword_score,
                "phrase_score": phrase_score,
                "is_neighbor": False
            })

        scored_chunks.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        relevant_chunks = [
            chunk
            for chunk in scored_chunks
            if chunk["score"] > 0
        ]

        if not relevant_chunks:
            return []

        selected = relevant_chunks[
            :self.top_k
        ]

        selected_ids = {
            chunk["chunk_id"]
            for chunk in selected
        }

        chunks_by_id = {
            chunk["chunk_id"]: chunk
            for chunk in chunks
        }

        neighbors = []

        for chunk in list(selected):

            chunk_id = chunk["chunk_id"]

            for offset in range(
                1,
                self.neighbor_chunks + 1
            ):

                for neighbor_id in (
                    chunk_id - offset,
                    chunk_id + offset
                ):

                    if neighbor_id in selected_ids:
                        continue

                    neighbor = chunks_by_id.get(
                        neighbor_id
                    )

                    if neighbor is None:
                        continue

                    neighbors.append({
                        **neighbor,
                        "score": 0.0,
                        "semantic_score": 0.0,
                        "tfidf_score": 0.0,
                        "keyword_score": 0.0,
                        "phrase_score": 0.0,
                        "is_neighbor": True
                    })

                    selected_ids.add(
                        neighbor_id
                    )

        selected.extend(neighbors)

        selected.sort(
            key=lambda x: x["chunk_id"]
        )

        return selected