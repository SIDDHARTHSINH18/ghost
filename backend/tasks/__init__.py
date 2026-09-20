"""
GHOST — task domain package.

Model: backend/core/task.py (Task, TaskStatus)
Service: backend/tasks/service.py (TaskService)

The package exposes the service for convenient import:
    from backend.tasks import TaskService
"""

from backend.tasks.service import TaskService

__all__ = ["TaskService"]
