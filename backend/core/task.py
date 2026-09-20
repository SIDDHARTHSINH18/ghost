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
    result: str | None = None
    error: str | None = None
    # Populated by the post-execution reflection stage. Kept
    # deliberately untyped here so core.task remains independent
    # from the reflection package.
    reflection: Any = None
