from datetime import datetime
from backend.core.task import Task, TaskStatus


def test_task_creation():
    task = Task(title="Test Task", description="Test Description")
    assert task.title == "Test Task"
    assert task.description == "Test Description"
    assert isinstance(task.id, str)
    assert task.status == TaskStatus.PENDING
    assert task.priority == 1
    assert isinstance(task.created_at, datetime)
    assert isinstance(task.updated_at, datetime)
    assert task.result is None
    assert task.error is None

def test_task_defaults():
    task = Task(title="Test Task", description="Test Description")
    assert task.status == TaskStatus.PENDING
    assert task.priority == 1
    assert task.result is None
    assert task.error is None

def test_task_uuid_generation():
    task1 = Task(title="Task 1", description="Description 1")
    task2 = Task(title="Task 2", description="Description 2")
    assert task1.id != task2.id

def test_task_timestamps():
    task = Task(title="Test Task", description="Test Description")
    assert task.created_at <= task.updated_at

def test_task_result_error_defaults():
    task = Task(title="Test Task", description="Test Description")
    assert task.result is None
    assert task.error is None

def test_task_status_values():
    assert TaskStatus.PENDING.value == "PENDING"
    assert TaskStatus.RUNNING.value == "RUNNING"
    assert TaskStatus.COMPLETED.value == "COMPLETED"
    assert TaskStatus.FAILED.value == "FAILED"
    assert TaskStatus.CANCELLED.value == "CANCELLED"
