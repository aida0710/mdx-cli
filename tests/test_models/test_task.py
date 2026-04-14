from mdx_cli.models.task import Task


def test_task_from_dict():
    data = {
        "uuid": "task-123",
        "type": "デプロイ",
        "object_uuid": "vm-456",
        "object_name": "test-vm",
        "start_datetime": "2026-04-14 16:34:13",
        "end_datetime": None,
        "status": "Running",
        "progress": 63,
    }
    task = Task.model_validate(data)
    assert task.uuid == "task-123"
    assert task.progress == 63
    assert task.is_terminal is False


def test_task_completed_is_terminal():
    data = {
        "uuid": "task-123",
        "type": "デプロイ",
        "object_uuid": "vm-456",
        "object_name": "test-vm",
        "start_datetime": "2026-04-14 16:34:13",
        "end_datetime": "2026-04-14 16:40:00",
        "status": "Completed",
        "progress": 100,
    }
    task = Task.model_validate(data)
    assert task.is_terminal is True


def test_task_failed_is_terminal():
    data = {
        "uuid": "task-123",
        "type": "デプロイ",
        "object_uuid": "vm-456",
        "object_name": "test-vm",
        "start_datetime": "2026-04-14 16:34:13",
        "end_datetime": "2026-04-14 16:40:00",
        "status": "Failed",
        "progress": 50,
    }
    task = Task.model_validate(data)
    assert task.is_terminal is True
