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
        owner: str | None = None,
    ) -> Task:
        """
        Create and store a new Task. Returns the task.

        ``owner`` is the hashed session identity of the
        authenticated creator (None for legacy/in-process
        tasks, which stay visible to every session).
        """

        if not title or not title.strip():
            raise ValueError("Task title cannot be empty.")

        task = Task(
            title=title.strip(),
            description=description or "",
            owner=owner,
        )

        self._tasks[task.id] = task

        return task

    def get(self, task_id: str, owner: str | None = None) -> Task:
        """
        Return the task for a known ID. Unknown IDs raise
        KeyError. When ``owner`` is given, a task owned by a
        DIFFERENT session also raises KeyError — callers report
        the same 404 either way, so the existence of another
        user's task is never revealed.
        """

        if task_id not in self._tasks:
            raise KeyError(f"Task '{task_id}' not found.")

        task = self._tasks[task_id]

        if (
            owner is not None
            and task.owner is not None
            and task.owner != owner
        ):
            raise KeyError(f"Task '{task_id}' not found.")

        return task

    def list(self, owner: str | None = None) -> List[Task]:
        """
        Return stored tasks ordered by creation time
        (deterministic; ties broken by id).

        With ``owner``, only that owner's tasks plus legacy
        owner-less tasks are returned.
        """

        return sorted(
            (
                task
                for task in self._tasks.values()
                if task.owner is None or owner is None
                or task.owner == owner
            ),
            key=lambda task: (task.created_at, task.id),
        )

    def count(self) -> int:
        return len(self._tasks)
