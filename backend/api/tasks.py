"""
GHOST — live task entry point (M3-H step 4, M4 step 8).

Connects the live application to the planning/task
architecture:

  user request -> API -> AgentPipeline
    -> Planner -> ExecutionSpec -> SkillStage
    -> TaskRunner -> AutomationEngine -> Agent
    -> PermissionPolicy -> ToolRegistry
    -> Reflection -> MemoryBridge -> AuditLog

Boundaries honored here:
- This module is an HTTP adapter, not an orchestrator: the
  pipeline owns the stage order, and every component it uses
  is the shared singleton from backend.core.agent_services
  (no second planner, task store, runner or registry).
- The ONLY model access is the existing orchestrator
  gateway singleton (backend.core.services). No new
  provider, no second orchestrator.
- One request is awaited, never blocked: no asyncio.run(),
  no nested event loop, no thread bridge, so a plan that
  calls the model gateway cannot stall the server loop.
- A ready plan whose steps name registered tools is
  executed through the existing TaskRunner -> Agent ->
  PermissionPolicy -> ToolRegistry pipeline: SAFE steps
  run, SENSITIVE steps pause for explicit approval,
  DANGEROUS/unknown tools fail closed. Tool-less steps
  are advisory and are never executed.
- Clarification rounds create NO task: the planner's
  questions are returned cleanly and the store is left
  untouched until enough information exists.
- Every response carries the full, auditable planning
  result (source, parse status, questions, assumptions,
  raw model output) so what happened after planning is
  deterministic and inspectable.
- Authentication is enforced by the existing session
  middleware (/api/tasks is not a public path).
"""

import logging

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from backend.agents.pipeline import AgentPipeline
from backend.approval.service import (
    ApprovalDeniedError,
    ApprovalRequiredError,
)
from backend.core.agent_services import (
    approval_service,
    audit_log,
    memory_bridge,
    planner,
    reflection_engine,
    skill_stage,
    task_runner,
    task_service,
    tool_registry,
)


logger = logging.getLogger(
    "ghost.tasks",
)


router = APIRouter(
    prefix="/api",
    tags=["Tasks"],
)


# ============================================================
# PIPELINE WIRING
# ============================================================

def build_pipeline() -> AgentPipeline:
    """
    Compose the agent chain from this module's component
    singletons.

    The stages themselves live in backend.core.agent_services;
    this function only names their order for one request. The
    components are read here (not captured at import time) so a
    caller — a test, or a future request-scoped wiring — can
    substitute one component without mutating process state.
    """

    return AgentPipeline(
        planner=planner,
        task_service=task_service,
        task_runner=task_runner,
        tool_registry=tool_registry,
        skill_stage=skill_stage,
        reflection_engine=reflection_engine,
        memory_bridge=memory_bridge,
        audit=audit_log,
    )


# ============================================================
# REQUEST MODEL
# ============================================================

class HistoryTurn(BaseModel):
    role: str
    content: str


class TaskRequest(BaseModel):
    request: str

    # Optional planning context, mirroring the gateway.
    memory_context: str | None = None
    document_context: str | None = None
    conversation_history: list[HistoryTurn] = []


class ApprovalDecision(BaseModel):
    approved: bool


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/tasks")
async def create_task_from_request(
    body: TaskRequest,
    response: Response,
):
    """
    Plan a user request, then — only when the plan is
    ready — create, store and run its task through the
    agent pipeline.

    Outcomes (deterministic, auditable):
    - 201 {"status": "created", "task_id": ...}   ready plan, task stored
    - 200 {"status": "clarification_required"}    questions, NO task
    - 400 empty request                           no planning at all
    """

    request_text = (body.request or "").strip()

    if not request_text:
        raise HTTPException(
            status_code=400,
            detail="Request cannot be empty.",
        )

    history = (
        [
            {"role": turn.role, "content": turn.content}
            for turn in body.conversation_history
            if turn.content.strip()
        ]
        if body.conversation_history
        else None
    )

    outcome = await build_pipeline().handle_request(
        request_text,
        memory_context=body.memory_context,
        document_context=body.document_context,
        conversation_history=history,
    )

    planning = outcome.planning

    # --------------------------------------------------------
    # Clarification round: represented cleanly, nothing
    # created, nothing executed.
    # --------------------------------------------------------

    if outcome.clarification_required:
        return {
            "status": "clarification_required",
            "questions": planning.questions,
            "planning": planning.to_dict(),
        }

    task = outcome.task

    logger.info(
        "Task planned and created id=%s source=%s "
        "planner_parse_ok=%s steps=%d",
        task.id,
        planning.source.value,
        planning.parse_ok,
        len(planning.steps),
    )

    # 201 Created — deterministic distinction from the
    # 200 clarification round above.
    response.status_code = 201

    execution = outcome.execution

    return {
        "status": "created",
        "task_id": task.id,
        "task": {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
        },
        "planning": planning.to_dict(),
        "execution": execution,
    }



@router.get("/tasks")
async def list_tasks():
    """List all stored tasks (metadata only)."""

    tasks = task_service.list()

    return {
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "status": task.status.value,
                "created_at": task.created_at.isoformat(),
            }
            for task in tasks
        ],
        "total": len(tasks),
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Return one stored task by ID."""

    try:
        task = task_service.get(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found.",
        )

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "result": task.result,
        "error": task.error,
        "reflection": (
            task.reflection.to_dict()
            if task.reflection is not None
            else None
        ),
    }


# ============================================================
# APPROVAL + RESUME (M3-H step 5, M4 step 8)
# ============================================================
#
# Decision and execution are separate, explicit steps:
# POST /approvals/{id}/decision records the human
# decision (never executes); POST /tasks/{id}/resume
# continues an approved workflow through the normal
# Agent -> PermissionPolicy -> ToolRegistry path. No
# arbitrary tool execution exists on either endpoint.
# The pipeline adds the audit/memory record around those
# runner calls; it changes no decision and no shape.

@router.get("/approvals")
async def list_pending_approvals():
    """List approvals awaiting a decision (audit view)."""

    pending = approval_service.list_pending()

    return {
        "approvals": [
            record.to_dict() for record in pending
        ],
        "total": len(pending),
    }


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
):
    """
    Record an explicit approval decision. Unknown IDs
    fail safely (404); already-decided approvals are
    refused (409) — no silent overrides.
    """

    pipeline = build_pipeline()

    try:
        record = approval_service.decide(
            approval_id,
            approved=body.approved,
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Approval '{approval_id}' not found.",
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

    # ApprovalService owns the decision record; the pipeline
    # only puts the event on the audit trail.
    pipeline.record_approval_decision(record)

    if not body.approved:
        # The decision itself remains in ApprovalService. The
        # runner records the corresponding terminal workflow
        # state and passes its real denial artifact to reflection.
        await pipeline.finalize_denied_approval(approval_id)

    logger.info(
        "Approval %s decided status=%s task=%s tool=%s",
        record.approval_id,
        record.status.value,
        record.task_id,
        record.tool_name,
    )

    return {
        "approval_id": record.approval_id,
        "status": record.status.value,
        "task_id": record.task_id,
        "tool_name": record.tool_name,
        "decided_at": record.decided_at,
    }


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """
    Resume a paused task after explicit approval. Every
    refusal reason is reported explicitly; resumption
    always flows through PermissionPolicy.
    """

    try:
        outcome = await build_pipeline().resume(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found.",
        )
    except ApprovalDeniedError:
        raise HTTPException(
            status_code=409,
            detail=(
                "Approval for this task was denied; "
                "resume refused."
            ),
        )
    except ApprovalRequiredError:
        raise HTTPException(
            status_code=409,
            detail=(
                "Task is awaiting an approval decision; "
                "resume refused."
            ),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

    task = task_service.get(task_id)

    logger.info(
        "Task %s resumed state=%s task_status=%s",
        task_id,
        outcome["state"].value,
        task.status.value,
    )

    return {
        "status": outcome["state"].value,
        "task_id": task_id,
        "task_status": task.status.value,
        "approval_id": outcome.get("approval_id"),
        "result": task.result,
        "error": task.error,
        "reflection": outcome.get("reflection"),
    }
