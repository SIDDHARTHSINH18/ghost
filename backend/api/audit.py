"""
GHOST — audit trail endpoint (M4 step 10).

Read-only view over the one append-only AuditLog store
(backend/audit/log.py). There is deliberately no write,
update or delete route: the pipeline is the only writer, and
rows reach disk sanitized (credential keys dropped,
credential-shaped text redacted, long values truncated), so
this endpoint exposes an already-safe record rather than
re-trusting the client.

Authentication comes from the existing session middleware
(/api/audit is not a public path).
"""

from fastapi import APIRouter, HTTPException, Query

from backend.audit.log import AuditStage
from backend.core.agent_services import audit_log


router = APIRouter(
    prefix="/api",
    tags=["Audit"],
)


# The store is unbounded, so a listing must be: the most
# recent rows are what an operator asks for.
DEFAULT_LIMIT = 200

MAX_LIMIT = 1000


@router.get("/audit")
async def read_audit(
    task_id: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    Return stored audit rows in append order, newest-truncated
    to ``limit``: filters narrow by task and/or pipeline stage.
    """

    stage_value = _validated_stage(stage)

    rows = audit_log.read(
        task_id=task_id,
        stage=stage_value,
        limit=limit,
    )

    return {
        "rows": rows,
        "total": len(rows),
        "task_id": task_id,
        "stage": stage_value,
        "limit": limit,
    }


def _validated_stage(stage: str | None) -> str | None:
    """Reject an unknown stage instead of silently returning nothing."""

    if stage is None or not stage.strip():
        return None

    wanted = stage.strip().lower()

    for member in AuditStage:
        if member.value == wanted:
            return member.value

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unknown audit stage '{stage}'. "
            "Expected one of: "
            f"{', '.join(member.value for member in AuditStage)}."
        ),
    )
