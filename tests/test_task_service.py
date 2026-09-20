import pytest

from backend.tasks.service import TaskService


def test_create_stores_and_returns_task():
    service = TaskService()
    task = service.create(title="Test Task", description="Do the thing")
    assert service.get(task.id) is task
    assert service.count() == 1


def test_create_strips_title_whitespace():
    service = TaskService()
    task = service.create(title="  Padded Title  ")
    assert task.title == "Padded Title"


def test_create_rejects_empty_title():
    service = TaskService()
    with pytest.raises(ValueError):
        service.create(title="")
    with pytest.raises(ValueError):
        service.create(title="   ")


def test_create_defaults_description_to_empty_string():
    service = TaskService()
    task = service.create(title="No description")
    assert task.description == ""


def test_create_generates_unique_ids():
    service = TaskService()
    task1 = service.create(title="First")
    task2 = service.create(title="Second")
    assert task1.id != task2.id
    assert service.count() == 2


def test_get_unknown_id_raises_keyerror():
    service = TaskService()
    with pytest.raises(KeyError, match="no-such-id"):
        service.get("no-such-id")


def test_list_empty_returns_empty_list():
    service = TaskService()
    assert service.list() == []


def test_list_ordered_by_creation_then_id():
    service = TaskService()
    tasks = [service.create(title=f"Task {i}") for i in range(5)]
    listed = service.list()
    assert [t.id for t in listed] == [t.id for t in tasks]


def test_count_tracks_number_of_tasks():
    service = TaskService()
    assert service.count() == 0
    service.create(title="One")
    service.create(title="Two")
    assert service.count() == 2
