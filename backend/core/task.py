from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4
from datetime import datetime

class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

@dataclass
class Task:
    title: str
    description: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    retry_count: int = 0
    # Cooperative cancellation flag: set by TaskService.cancel;
    # the engine observes it at step boundaries because the
    # status field alone is overwritten during step execution.
    cancel_requested: bool = False
    # Hashed session identity of the authenticated creator.
    # None = legacy/in-process task (not HTTP-created); such
    # tasks remain visible to every authenticated session.
    owner: str | None = None
    # Free-form lifecycle metadata (planning source, provider,
    # etc.). Never credentials.
    metadata: dict = field(default_factory=dict)
    # Populated by the post-execution reflection stage. Kept
    # deliberately untyped here so core.task remains independent
    # from the reflection package.
    reflection: Any = None


# Explicit state machine. Every status change must go through
# TaskService, which validates against this map — nothing else
# in the codebase may assign Task.status directly (engine steps
# transition PENDING→RUNNING→terminal through the service).
VALID_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.RUNNING,
        TaskStatus.FAILED,  # planning/queue-time failures
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.PENDING,  # paused/approval flows return to PENDING
    },
    TaskStatus.COMPLETED: set(),  # terminal
    TaskStatus.FAILED: {
        TaskStatus.PENDING,  # controlled retry re-queues the task
    },
    TaskStatus.CANCELLED: set(),  # terminal
}

MAX_TASK_RETRIES = 3


def can_transition(current: TaskStatus, new: TaskStatus) -> bool:
    return new in VALID_TASK_TRANSITIONS[current]
