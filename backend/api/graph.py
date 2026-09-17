import logging

from fastapi import APIRouter

from backend.core.services import documents, memory_service


logger = logging.getLogger(
    "ghost.graph",
)


router = APIRouter(
    prefix="/api",
    tags=["Graph"],
)


# Privacy (docs/05-privacy-assessment.md §3.4): the graph
# previously returned full memory content to any caller.
# It now returns counts and truncated labels only; memory
# content is available exclusively through the
# authenticated memory API (M1).

MAX_MEMORY_NODES = 12

MAX_LABEL_LENGTH = 38


def shorten(
    text,
    length=45,
):

    text = (
        str(text)
        .replace("\n", " ")
        .strip()
    )

    if len(text) <= length:
        return text

    return (
        text[:length - 3]
        + "..."
    )


@router.get("/graph")
async def get_graph():
    """
    Return the current GHOST knowledge/access graph.

    The frontend uses this endpoint to visualize:
    - GHOST core
    - documents
    - memories (labels only, never content)
    - projects
    - tools
    - tasks
    """

    nodes = []
    edges = []

    # ============================================================
    # GHOST CORE
    # ============================================================

    nodes.append({
        "id": "GHOST",
        "type": "GHOST",
        "label": "GHOST",
        "description": "Personal AI operating system.",
    })

    # ============================================================
    # DOCUMENTS (metadata only, never document text)
    # ============================================================

    for document_id, document in documents.items():

        filename = document.get(
            "filename",
            "Unknown document",
        )

        chunks = document.get(
            "chunks",
            [],
        )

        pages = document.get(
            "pages",
            [],
        )

        node_id = f"document-{document_id}"

        nodes.append({
            "id": node_id,
            "type": "document",
            "label": filename,
            "description": (
                "Indexed document available to GHOST."
            ),
            "document_id": document_id,
            "chunks": len(chunks),
            "pages": len(pages),
            "status": "indexed",
        })

        edges.append({
            "source": "GHOST",
            "target": node_id,
            "type": "access",
        })

    # ============================================================
    # MEMORY (counts + truncated labels only)
    # ============================================================

    memory_root = {
        "id": "memory-root",
        "type": "memory",
        "label": "Memory",
        "description": (
            "GHOST's persistent conversation memory."
        ),
    }

    nodes.append(memory_root)

    edges.append({
        "source": "GHOST",
        "target": "memory-root",
        "type": "access",
    })

    memory_items = []

    try:

        # Single shared instance (defect D3 fixed in M0);
        # read-only access here.
        memory_items = list(
            memory_service.memories
        )

    except Exception as error:

        logger.warning(
            "Graph memory read failed: %s",
            type(error).__name__,
        )

    nodes.append({
        "id": "memory-count",
        "type": "memory",
        "label": f"{len(memory_items)} memories",
        "description": (
            f"{len(memory_items)} stored memory items."
        ),
    })

    edges.append({
        "source": "memory-root",
        "target": "memory-count",
        "type": "contains",
    })

    # Display up to MAX_MEMORY_NODES label-only nodes.
    # Labels are derived from type/index only — never
    # from content: short memories would otherwise
    # leak verbatim through the label (caught by
    # tests/test_main.py::test_graph_memory_labels_not_content).
    for index, memory in enumerate(
        memory_items[:MAX_MEMORY_NODES]
    ):

        if not isinstance(
            memory,
            dict,
        ):
            continue

        memory_type = memory.get(
            "memory_type",
        ) or memory.get(
            "type",
            "conversation",
        )

        node_id = f"memory-{index}"

        nodes.append({
            "id": node_id,
            "type": "memory",
            "label": shorten(
                f"memory · {memory_type}",
                MAX_LABEL_LENGTH,
            ),
            "description": (
                "Memory item (content hidden; use the "
                "memory API to inspect it)."
            ),
            "memory_type": memory_type,
        })

        edges.append({
            "source": "memory-root",
            "target": node_id,
            "type": "contains",
        })

    # ============================================================
    # PROJECTS
    # ============================================================

    nodes.append({
        "id": "project-GHOST",
        "type": "project",
        "label": "GHOST",
        "description": (
            "GHOST personal AI operating system."
        ),
    })

    edges.append({
        "source": "GHOST",
        "target": "project-GHOST",
        "type": "project",
    })

    # ============================================================
    # TOOLS
    # ============================================================

    tools = [
        {
            "id": "tool-nemotron",
            "label": "Nemotron",
            "description": (
                "NVIDIA Nemotron model provider."
            ),
            "status": "connected",
        },
        {
            "id": "tool-files",
            "label": "Files",
            "description": (
                "File access capability."
            ),
            "status": "planned",
        },
        {
            "id": "tool-browser",
            "label": "Browser",
            "description": (
                "Browser agent capability."
            ),
            "status": "planned",
        },
        {
            "id": "tool-pc",
            "label": "PC Agent",
            "description": (
                "Authenticated Windows PC agent."
            ),
            "status": "planned",
        },
        {
            "id": "tool-gmail",
            "label": "Gmail",
            "description": (
                "Authorized Gmail integration."
            ),
            "status": "planned",
        },
        {
            "id": "tool-telegram",
            "label": "Telegram",
            "description": (
                "Telegram gateway."
            ),
            "status": "planned",
        },
    ]

    for tool in tools:

        nodes.append({
            "id": tool["id"],
            "type": "tool",
            "label": tool["label"],
            "description": tool["description"],
            "status": tool["status"],
        })

        if tool["status"] == "connected":

            edges.append({
                "source": "GHOST",
                "target": tool["id"],
                "type": "tool",
            })

    # ============================================================
    # TASKS
    # ============================================================

    nodes.append({
        "id": "tasks-root",
        "type": "task",
        "label": "Tasks",
        "description": (
            "GHOST task execution system."
        ),
        "status": "planned",
    })

    edges.append({
        "source": "GHOST",
        "target": "tasks-root",
        "type": "tasks",
    })

    # ============================================================
    # STATISTICS
    # ============================================================

    return {
        "success": True,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "documents": len(documents),
            "memories": len(memory_items),
            "projects": 1,
            "tools": 1,
            "tasks": 0,
        },
    }
