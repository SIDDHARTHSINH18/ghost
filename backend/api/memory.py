"""
GHOST — Memory user-control API (M1).

Privacy stance (docs/05-privacy-assessment.md §3.3,
spec §35 "user visibility"):

- GET /api/memory returns full content ON PURPOSE:
  this is the dedicated memory endpoint and the user
  must be able to see what GHOST stored in order to
  exercise control over it.
- Content stays OFF every other endpoint (the graph
  endpoint returns labels only — preserved from M0)
  and out of all logs.
- Deletion verifies the memory is actually gone from
  persistent storage, not just from the response.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.core.services import memory_service


logger = logging.getLogger(
    "ghost.memory",
)


router = APIRouter(
    prefix="/api",
    tags=["Memory"],
)


@router.get("/memory")
async def list_memories():
    """
    List all stored memories with full metadata.

    Fields: id, content, type, importance, confidence,
    project, source, tags, created_at, updated_at,
    last_accessed.
    """

    memories = memory_service.get_all()

    return {
        "memories": memories,
        "total": len(memories),
    }


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """
    Delete one memory and verify removal from
    persistent storage.
    """

    deleted = memory_service.delete(memory_id)

    if not deleted:

        raise HTTPException(
            status_code=404,
            detail="Memory not found.",
        )

    # Verify: the memory must no longer be retrievable.
    verified = (
        memory_service.get(memory_id) is None
    )

    logger.info(
        "Memory deleted id=%s verified=%s",
        memory_id,
        verified,
    )

    return {
        "deleted": True,
        "verified": verified,
        "memory_id": memory_id,
    }


@router.delete("/memory")
async def clear_all_memories():
    """
    Forget everything: delete all memories and
    verify the store is empty afterwards.
    """

    cleared = memory_service.clear()

    verified = (
        memory_service.get_all() == []
        and cleared
    )

    logger.info(
        "All memories cleared verified=%s",
        verified,
    )

    return {
        "deleted": True,
        "verified": verified,
    }
