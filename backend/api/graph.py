from fastapi import APIRouter

from api.upload import documents
from core.memory import MemoryService


router = APIRouter(
    prefix="/api",
    tags=["Graph"]
)


memory_service = MemoryService()


@router.get("/graph")
async def get_graph():
    """
    Return the current FRIDAY knowledge/access graph.

    The frontend uses this endpoint to visualize:
    - FRIDAY core
    - documents
    - memories
    - projects
    - tools
    - tasks
    """

    nodes = []
    edges = []

    # ============================================================
    # FRIDAY CORE
    # ============================================================

    nodes.append({
        "id": "friday",
        "type": "friday",
        "label": "FRIDAY",
        "description": "Personal AI operating system.",
    })

    # ============================================================
    # DOCUMENTS
    # ============================================================

    for document_id, document in documents.items():

        filename = document.get(
            "filename",
            "Unknown document"
        )

        chunks = document.get(
            "chunks",
            []
        )

        pages = document.get(
            "pages",
            []
        )

        node_id = f"document-{document_id}"

        nodes.append({
            "id": node_id,
            "type": "document",
            "label": filename,
            "description": (
                "Indexed document available to FRIDAY."
            ),
            "document_id": document_id,
            "chunks": len(chunks),
            "pages": len(pages),
            "status": "indexed",
        })

        edges.append({
            "source": "friday",
            "target": node_id,
            "type": "access",
        })

    # ============================================================
    # MEMORY
    # ============================================================

    memory_root = {
        "id": "memory-root",
        "type": "memory",
        "label": "Memory",
        "description": (
            "FRIDAY's persistent conversation memory."
        ),
    }

    nodes.append(memory_root)

    edges.append({
        "source": "friday",
        "target": "memory-root",
        "type": "access",
    })

    # Try to access the current MemoryService safely.
    memory_items = []

    try:

        if hasattr(memory_service, "memories"):

            if isinstance(
                memory_service.memories,
                list
            ):
                memory_items = (
                    memory_service.memories
                )

            elif isinstance(
                memory_service.memories,
                dict
            ):
                memory_items = list(
                    memory_service.memories.values()
                )

        elif hasattr(
            memory_service,
            "memory"
        ):

            memory_data = (
                memory_service.memory
            )

            if isinstance(
                memory_data,
                list
            ):
                memory_items = memory_data

            elif isinstance(
                memory_data,
                dict
            ):
                memory_items = list(
                    memory_data.values()
                )

    except Exception as error:

        print(
            f"Graph memory read warning: {error}"
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

    # Display up to 12 memory nodes.
    for index, memory in enumerate(
        memory_items[:12]
    ):

        if not isinstance(
            memory,
            dict
        ):
            continue

        content = str(
            memory.get(
                "content",
                memory.get(
                    "text",
                    "Memory"
                )
            )
        )

        node_id = f"memory-{index}"

        nodes.append({
            "id": node_id,
            "type": "memory",
            "label": shorten(
                content,
                38
            ),
            "description": content,
            "memory_type": memory.get(
                "memory_type",
                "conversation"
            ),
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
        "id": "project-friday",
        "type": "project",
        "label": "FRIDAY",
        "description": (
            "FRIDAY personal AI operating system."
        ),
    })

    edges.append({
        "source": "friday",
        "target": "project-friday",
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
                "source": "friday",
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
            "FRIDAY task execution system."
        ),
        "status": "planned",
    })

    edges.append({
        "source": "friday",
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


def shorten(
    text,
    length=45
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