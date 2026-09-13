"""
FRIDAY Persistent Memory System

Stores long-term memories locally so FRIDAY can remember:
- Important user information
- Preferences
- Decisions
- Projects
- Conversation facts
- Useful context

Storage:
    backend/data/memory.json
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class MemoryService:
    """
    Persistent local memory service for FRIDAY.
    """

    def __init__(self, storage_path: str | None = None):
        if storage_path is None:
            backend_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            storage_path = os.path.join(
                backend_dir,
                "data",
                "memory.json"
            )

        self.storage_path = storage_path

        # Make sure the directory exists
        directory = os.path.dirname(self.storage_path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        # Load existing memories
        self.memories: List[Dict[str, Any]] = self._load()

    # ---------------------------------------------------------
    # LOAD / SAVE
    # ---------------------------------------------------------

    def _load(self) -> List[Dict[str, Any]]:
        """
        Load memories from disk.
        """

        if not os.path.exists(self.storage_path):
            return []

        try:
            with open(
                self.storage_path,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            if isinstance(data, list):
                return data

            return []

        except (json.JSONDecodeError, OSError):
            return []

    def _save(self) -> None:
        """
        Save memories to disk.
        """

        temp_path = self.storage_path + ".tmp"

        with open(
            temp_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                self.memories,
                file,
                indent=2,
                ensure_ascii=False
            )

        # Replace the old file safely
        os.replace(temp_path, self.storage_path)

    # ---------------------------------------------------------
    # ADD MEMORY
    # ---------------------------------------------------------

    def add_memory(
        self,
        content: str,
        memory_type: str = "general",
        importance: float = 0.5,
        project: Optional[str] = None,
        source: str = "conversation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a new long-term memory.
        """

        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty.")

        memory = {
            "id": str(uuid.uuid4()),
            "content": content.strip(),
            "type": memory_type,
            "importance": max(0.0, min(1.0, importance)),
            "project": project,
            "source": source,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        self.memories.append(memory)

        self._save()

        return memory

    # ---------------------------------------------------------
    # SEARCH MEMORY
    # ---------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories using simple local keyword matching.

        This is intentionally lightweight for the first version.
        Later we can replace this with semantic/vector retrieval.
        """

        if not query:
            return []

        query_words = set(
            word.lower()
            for word in query.split()
            if len(word.strip()) > 2
        )

        results = []

        for memory in self.memories:

            # Type filter
            if memory_type:
                if memory.get("type") != memory_type:
                    continue

            # Project filter
            if project:
                if memory.get("project") != project:
                    continue

            content = memory.get("content", "").lower()

            score = 0

            for word in query_words:
                if word in content:
                    score += 1

            # Importance contributes slightly
            score += memory.get("importance", 0.5) * 0.25

            if score > 0:
                result = dict(memory)
                result["_score"] = score
                results.append(result)

        # Highest relevance first
        results.sort(
            key=lambda item: item["_score"],
            reverse=True
        )

        # Remove internal score before returning
        for result in results:
            result.pop("_score", None)

        return results[:limit]

    # ---------------------------------------------------------
    # GET ALL
    # ---------------------------------------------------------

    def get_all(
        self,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Return stored memories.
        """

        memories = list(self.memories)

        if limit is not None:
            memories = memories[-limit:]

        return memories

    # ---------------------------------------------------------
    # GET ONE
    # ---------------------------------------------------------

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a memory by ID.
        """

        for memory in self.memories:
            if memory.get("id") == memory_id:
                return memory

        return None

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        project: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing memory.
        """

        memory = self.get(memory_id)

        if memory is None:
            return None

        if content is not None:
            memory["content"] = content.strip()

        if importance is not None:
            memory["importance"] = max(
                0.0,
                min(1.0, importance)
            )

        if project is not None:
            memory["project"] = project

        if metadata is not None:
            memory["metadata"] = metadata

        memory["updated_at"] = datetime.utcnow().isoformat()

        self._save()

        return memory

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory.
        """

        original_length = len(self.memories)

        self.memories = [
            memory
            for memory in self.memories
            if memory.get("id") != memory_id
        ]

        deleted = len(self.memories) < original_length

        if deleted:
            self._save()

        return deleted

    # ---------------------------------------------------------
    # CLEAR
    # ---------------------------------------------------------

    def clear(self) -> None:
        """
        Delete all memories.
        """

        self.memories = []

        self._save()

    # ---------------------------------------------------------
    # MEMORY CONTEXT
    # ---------------------------------------------------------

    def build_context(
        self,
        query: str,
        limit: int = 5
    ) -> str:
        """
        Convert retrieved memories into context that FRIDAY
        can receive through the orchestrator.
        """

        memories = self.search(
            query=query,
            limit=limit
        )

        if not memories:
            return ""

        lines = [
            "Relevant long-term memory:"
        ]

        for memory in memories:
            memory_type = memory.get(
                "type",
                "general"
            )

            content = memory.get(
                "content",
                ""
            )

            project = memory.get("project")

            if project:
                lines.append(
                    f"- [{memory_type}] "
                    f"[Project: {project}] "
                    f"{content}"
                )
            else:
                lines.append(
                    f"- [{memory_type}] {content}"
                )

        return "\n".join(lines)