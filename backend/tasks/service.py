"""
GHOST — production task service (M3-H step 2).

In-process store around the existing Task model
(backend/core/task.py). The service owns task
lifecycle bookkeeping only: no execution, no
approval, no planning, no persistence — those live
elsewhere (Agent/AutomationEngine now; approval and
planner in later steps).

Dependency direction is one-way:
    backend/tasks/service.py -> backend/core/task.py
Never the reverse.
"""

from typing import Dict, List

from backend.core.task import Task


class TaskService:
    """
    Minimal synchronous in-memory task store.

    Keys are Task.id (UUID4 strings assigned by the
    model's default_factory, so every stored task has
    a unique identity by construction).
    """

    def __init__(self):
        self._tasks: Dict[str, Task] = {}

    def create(
        self,
        title: str,
        description: str = "",
    ) -> Task:
        """
        Create and store a new Task. Returns the task.
        """

        if not title or not title.strip():
            raise ValueError("Task title cannot be empty.")

        task = Task(
            title=title.strip(),
            description=description or "",
        )

        self._tasks[task.id] = task

        return task

    def get(self, task_id: str) -> Task:
        """
        Return the task for a known ID. Unknown IDs
        raise KeyError with a clear, deterministic
        message.
        """

        if task_id not in self._tasks:
            raise KeyError(f"Task '{task_id}' not found.")

        return self._tasks[task_id]

    def list(self) -> List[Task]:
        """
        Return all stored tasks, ordered by creation
        time (deterministic; ties broken by id).
        """

        return sorted(
            self._tasks.values(),
            key=lambda task: (task.created_at, task.id),
        )

    def count(self) -> int:
        return len(self._tasks)
