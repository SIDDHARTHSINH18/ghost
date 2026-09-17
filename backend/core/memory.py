"""
GHOST — Advanced Persistent Memory System

Purpose:
    Persistent second-brain memory for GHOST.

Features:
    - Persistent JSON storage
    - Semantic-style keyword retrieval
    - Importance and confidence scoring
    - Recency weighting
    - Project association
    - Memory types
    - Tags
    - Duplicate detection
    - Context generation
    - Memory statistics
    - Safe CRUD operations
    - Backward compatibility with existing memory records
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class MemoryService:
    """
    Persistent memory service for GHOST.

    Memory structure:

    {
        "id": "...",
        "content": "...",
        "type": "general",
        "importance": 0.8,
        "confidence": 1.0,
        "project": "GHOST",
        "source": "user",
        "tags": ["project", "preference"],
        "metadata": {},
        "created_at": "...",
        "updated_at": "...",
        "last_accessed": "..."
    }
    """

    # ---------------------------------------------------------
    # INITIALIZATION
    # ---------------------------------------------------------

    def __init__(
        self,
        storage_path: Optional[str] = None,
    ):
        """
        Initialize persistent memory.

        If no storage path is provided, memory is stored at:

            project_root/backend/data/memory.json
        """

        if storage_path is None:
            current_file = os.path.abspath(__file__)

            # backend/core/memory.py
            # -> backend/core
            # -> backend
            project_root = os.path.abspath(
                os.path.join(
                    os.path.dirname(current_file),
                    "..",
                    "..",
                )
            )

            storage_path = os.path.join(
                project_root,
                "backend",
                "data",
                "memory.json",
            )

        self.storage_path = os.path.abspath(storage_path)

        directory = os.path.dirname(self.storage_path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        self.memories: List[Dict[str, Any]] = self._load()

    # ---------------------------------------------------------
    # TIME
    # ---------------------------------------------------------

    def _now(self) -> str:
        """Return current UTC timestamp."""

        return datetime.now(timezone.utc).isoformat()

    # ---------------------------------------------------------
    # STORAGE
    # ---------------------------------------------------------

    def _load(self) -> List[Dict[str, Any]]:
        """
        Load memories from disk.

        Corrupted or missing files safely return an empty list.
        """

        if not os.path.exists(self.storage_path):
            return []

        try:
            with open(
                self.storage_path,
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if not isinstance(data, list):
                return []

            normalized = []

            for memory in data:
                if isinstance(memory, dict):
                    normalized.append(
                        self._normalize_memory(memory)
                    )

            return normalized

        except Exception as error:
            print(
                f"GHOST Memory Load Error: {error}"
            )
            return []

    def _save(self) -> bool:
        """
        Save memories safely to disk.
        """

        try:
            directory = os.path.dirname(
                self.storage_path
            )

            if directory:
                os.makedirs(
                    directory,
                    exist_ok=True,
                )

            temp_path = (
                self.storage_path + ".tmp"
            )

            with open(
                temp_path,
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    self.memories,
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

            os.replace(
                temp_path,
                self.storage_path,
            )

            return True

        except Exception as error:
            print(
                f"GHOST Memory Save Error: {error}"
            )
            return False

    # ---------------------------------------------------------
    # NORMALIZATION
    # ---------------------------------------------------------

    def _normalize_memory(
        self,
        memory: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Upgrade old memory records into the current format.
        """

        now = self._now()

        content = str(
            memory.get("content", "")
        ).strip()

        memory_type = (
            memory.get("type")
            or memory.get("memory_type")
            or "general"
        )

        try:
            importance = float(
                memory.get(
                    "importance",
                    0.5,
                )
            )
        except Exception:
            importance = 0.5

        try:
            confidence = float(
                memory.get(
                    "confidence",
                    1.0,
                )
            )
        except Exception:
            confidence = 1.0

        importance = max(
            0.0,
            min(1.0, importance),
        )

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        tags = memory.get(
            "tags",
            [],
        )

        if isinstance(tags, str):
            tags = [tags]

        if not isinstance(tags, list):
            tags = []

        metadata = memory.get(
            "metadata",
            {},
        )

        if not isinstance(metadata, dict):
            metadata = {}

        normalized = {
            "id": memory.get(
                "id",
                str(uuid.uuid4()),
            ),

            "content": content,

            "type": memory_type,

            "importance": importance,

            "confidence": confidence,

            "project": memory.get(
                "project"
            ),

            "source": memory.get(
                "source",
                "unknown",
            ),

            "tags": tags,

            "metadata": metadata,

            "created_at": memory.get(
                "created_at",
                now,
            ),

            "updated_at": memory.get(
                "updated_at",
                now,
            ),

            "last_accessed": memory.get(
                "last_accessed"
            ),
        }

        return normalized

    # ---------------------------------------------------------
    # TEXT PROCESSING
    # ---------------------------------------------------------

    def _tokenize(
        self,
        text: str,
    ) -> List[str]:
        """
        Convert text into searchable tokens.
        """

        if not text:
            return []

        return re.findall(
            r"\b[a-zA-Z0-9_'-]+\b",
            text.lower(),
        )

    def _normalize_text(
        self,
        text: str,
    ) -> str:
        return " ".join(
            str(text)
            .lower()
            .strip()
            .split()
        )

    # ---------------------------------------------------------
    # DUPLICATE DETECTION
    # ---------------------------------------------------------

    def _is_duplicate(
        self,
        content: str,
        project: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Detect an existing memory with identical normalized content.
        """

        normalized = self._normalize_text(
            content
        )

        for memory in self.memories:

            existing = self._normalize_text(
                memory.get(
                    "content",
                    "",
                )
            )

            if existing != normalized:
                continue

            existing_project = memory.get(
                "project"
            )

            if project is None or existing_project == project:
                return memory

        return None

    # ---------------------------------------------------------
    # ADD MEMORY
    # ---------------------------------------------------------

    def add_memory(
        self,
        content: str,
        memory_type: str = "general",
        importance: float = 0.5,
        project: Optional[str] = None,
        source: str = "user",
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a new persistent memory.

        Duplicate memories are not blindly duplicated.
        Existing memory importance/confidence can be upgraded.
        """

        content = str(content).strip()

        if not content:
            return {}

        importance = max(
            0.0,
            min(1.0, float(importance)),
        )

        confidence = max(
            0.0,
            min(1.0, float(confidence)),
        )

        duplicate = self._is_duplicate(
            content,
            project,
        )

        if duplicate:

            changed = False

            if importance > duplicate.get(
                "importance",
                0.5,
            ):
                duplicate["importance"] = importance
                changed = True

            if confidence > duplicate.get(
                "confidence",
                1.0,
            ):
                duplicate["confidence"] = confidence
                changed = True

            if tags:

                existing_tags = duplicate.get(
                    "tags",
                    [],
                )

                for tag in tags:
                    if tag not in existing_tags:
                        existing_tags.append(tag)
                        changed = True

                duplicate["tags"] = existing_tags

            duplicate["last_accessed"] = self._now()

            if changed:
                duplicate["updated_at"] = self._now()

            self._save()

            return duplicate

        now = self._now()

        memory = {
            "id": str(uuid.uuid4()),

            "content": content,

            "type": memory_type,

            "importance": importance,

            "confidence": confidence,

            "project": project,

            "source": source,

            "tags": tags or [],

            "metadata": metadata or {},

            "created_at": now,

            "updated_at": now,

            "last_accessed": None,
        }

        self.memories.append(memory)

        self._save()

        return memory

    # ---------------------------------------------------------
    # SEARCH
    # ---------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search persistent memories.

        Ranking considers:

        - Exact phrase matches
        - Keyword matches
        - Memory importance
        - Confidence
        - Recency
        - Project relevance
        - Memory type relevance
        """

        if not query:
            return []

        query_normalized = self._normalize_text(
            query
        )

        query_tokens = set(
            self._tokenize(query)
        )

        if not query_tokens:
            return []

        results = []

        now = datetime.now(
            timezone.utc
        )

        for memory in self.memories:

            content = memory.get(
                "content",
                "",
            )

            if not content:
                continue

            if memory_type:

                if memory.get("type") != memory_type:
                    continue

            if project:

                if memory.get("project") != project:
                    continue

            content_normalized = (
                self._normalize_text(
                    content
                )
            )

            content_tokens = set(
                self._tokenize(content)
            )

            # ---------------------------------------------
            # RELEVANCE GATE
            #
            # Importance, confidence and recency are
            # quality signals, not relevance signals.
            # Without a keyword/phrase match, every
            # memory would score > 0 for every query
            # and irrelevant memories would pollute
            # prompts (caught by tests).
            # ---------------------------------------------

            # ---------------------------------------------
            # KEYWORD SCORE
            # ---------------------------------------------

            matching_tokens = (
                query_tokens
                & content_tokens
            )

            keyword_score = (
                len(matching_tokens)
                / max(len(query_tokens), 1)
            )

            # ---------------------------------------------
            # PHRASE SCORE
            # ---------------------------------------------

            phrase_score = 0.0

            if query_normalized in content_normalized:
                phrase_score = 1.0

            if (
                keyword_score <= 0
                and phrase_score <= 0
            ):
                continue

            # ---------------------------------------------
            # IMPORTANCE
            # ---------------------------------------------

            importance = float(
                memory.get(
                    "importance",
                    0.5,
                )
            )

            # ---------------------------------------------
            # CONFIDENCE
            # ---------------------------------------------

            confidence = float(
                memory.get(
                    "confidence",
                    1.0,
                )
            )

            # ---------------------------------------------
            # PROJECT SCORE
            # ---------------------------------------------

            project_score = 0.0

            memory_project = memory.get(
                "project"
            )

            if (
                memory_project
                and self._normalize_text(
                    str(memory_project)
                ) in query_normalized
            ):
                project_score = 1.0

            # ---------------------------------------------
            # TYPE SCORE
            # ---------------------------------------------

            type_score = 0.0

            memory_type_value = str(
                memory.get(
                    "type",
                    "",
                )
            ).lower()

            if (
                memory_type_value
                and memory_type_value in query_normalized
            ):
                type_score = 1.0

            # ---------------------------------------------
            # RECENCY SCORE
            # ---------------------------------------------

            recency_score = 0.0

            timestamp = memory.get(
                "updated_at"
            ) or memory.get(
                "created_at"
            )

            if timestamp:

                try:

                    memory_time = datetime.fromisoformat(
                        timestamp
                    )

                    if memory_time.tzinfo is None:
                        memory_time = memory_time.replace(
                            tzinfo=timezone.utc
                        )

                    age_days = max(
                        0.0,
                        (
                            now - memory_time
                        ).total_seconds()
                        / 86400,
                    )

                    # Recency slowly decays over time.
                    recency_score = (
                        1.0
                        / (1.0 + age_days / 30.0)
                    )

                except Exception:
                    recency_score = 0.0

            # ---------------------------------------------
            # FINAL SCORE
            # ---------------------------------------------

            score = (
                keyword_score * 0.42
                + phrase_score * 0.20
                + importance * 0.16
                + confidence * 0.08
                + recency_score * 0.08
                + project_score * 0.04
                + type_score * 0.02
            )

            if score <= 0:
                continue

            result = dict(memory)

            result["_score"] = round(
                score,
                4,
            )

            results.append(result)

        results.sort(
            key=lambda item: (
                item.get(
                    "_score",
                    0,
                ),
                item.get(
                    "importance",
                    0,
                ),
            ),
            reverse=True,
        )

        selected = results[:limit]

        # Update access timestamps.
        accessed = False

        for memory in selected:

            memory_id = memory.get("id")

            for stored in self.memories:

                if stored.get("id") == memory_id:

                    stored["last_accessed"] = self._now()

                    accessed = True

                    break

        if accessed:
            self._save()

        return selected

    # ---------------------------------------------------------
    # BUILD CONTEXT
    # ---------------------------------------------------------

    def build_context(
        self,
        query: str,
        limit: int = 5,
    ) -> str:
        """
        Build clean memory context for GHOST.

        This is the method used by chat.py.
        """

        memories = self.search(
            query=query,
            limit=limit,
        )

        if not memories:
            return ""

        context_parts = []

        for memory in memories:

            content = memory.get(
                "content",
                "",
            ).strip()

            if not content:
                continue

            memory_type = memory.get(
                "type",
                "general",
            )

            project = memory.get(
                "project"
            )

            confidence = memory.get(
                "confidence",
                1.0,
            )

            line = (
                f"- [{memory_type}] "
                f"{content}"
            )

            if project:
                line += (
                    f" "
                    f"(Project: {project})"
                )

            if confidence < 0.7:
                line += (
                    " "
                    "[low confidence]"
                )

            context_parts.append(
                line
            )

        return "\n".join(
            context_parts
        )

    # ---------------------------------------------------------
    # GET ALL
    # ---------------------------------------------------------

    def get_all(
        self,
        project: Optional[str] = None,
        memory_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return all memories with optional filters.
        """

        results = []

        for memory in self.memories:

            if project:

                if memory.get("project") != project:
                    continue

            if memory_type:

                if memory.get("type") != memory_type:
                    continue

            results.append(
                dict(memory)
            )

        return results

    # ---------------------------------------------------------
    # GET BY ID
    # ---------------------------------------------------------

    def get(
        self,
        memory_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get one memory by ID.
        """

        for memory in self.memories:

            if memory.get("id") == memory_id:

                memory["last_accessed"] = self._now()

                self._save()

                return dict(memory)

        return None

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    def update(
        self,
        memory_id: str,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing memory.
        """

        allowed_fields = {
            "content",
            "type",
            "memory_type",
            "importance",
            "confidence",
            "project",
            "source",
            "tags",
            "metadata",
        }

        for memory in self.memories:

            if memory.get("id") != memory_id:
                continue

            for key, value in updates.items():

                if key not in allowed_fields:
                    continue

                if key == "memory_type":
                    key = "type"

                if key == "importance":

                    try:
                        value = max(
                            0.0,
                            min(
                                1.0,
                                float(value),
                            ),
                        )

                    except Exception:
                        continue

                if key == "confidence":

                    try:
                        value = max(
                            0.0,
                            min(
                                1.0,
                                float(value),
                            ),
                        )

                    except Exception:
                        continue

                memory[key] = value

            memory["updated_at"] = self._now()

            self._save()

            return dict(memory)

        return None

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    def delete(
        self,
        memory_id: str,
    ) -> bool:
        """
        Delete one memory by ID.
        """

        original_count = len(
            self.memories
        )

        self.memories = [
            memory
            for memory in self.memories
            if memory.get("id") != memory_id
        ]

        changed = (
            len(self.memories)
            != original_count
        )

        if changed:
            self._save()

        return changed

    # ---------------------------------------------------------
    # CLEAR
    # ---------------------------------------------------------

    def clear(self) -> bool:
        """
        Clear all memories.
        """

        self.memories = []

        return self._save()

    # ---------------------------------------------------------
    # STATISTICS
    # ---------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """
        Return memory statistics.
        """

        type_counts: Dict[str, int] = {}

        project_counts: Dict[str, int] = {}

        for memory in self.memories:

            memory_type = memory.get(
                "type",
                "general",
            )

            type_counts[memory_type] = (
                type_counts.get(
                    memory_type,
                    0,
                )
                + 1
            )

            project = memory.get(
                "project"
            )

            if project:

                project_counts[project] = (
                    project_counts.get(
                        project,
                        0,
                    )
                    + 1
                )

        return {
            "total_memories": len(
                self.memories
            ),

            "types": type_counts,

            "projects": project_counts,

            "storage_path": self.storage_path,
        }