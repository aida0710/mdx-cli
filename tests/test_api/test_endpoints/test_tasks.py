import httpx
import respx

from mdx_cli.api.endpoints.tasks import get_task, wait_for_task
from mdx_cli.models.task import Task


@respx.mock
def test_get_task():
    respx.get("/api/task/task-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "task-1",
                "type": "デプロイ",
                "object_uuid": "vm-1",
                "object_name": "test-vm",
                "start_datetime": "2026-04-14 16:34:13",
                "end_datetime": None,
                "status": "Running",
                "progress": 50,
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    task = get_task(client, "task-1")
    assert task.uuid == "task-1"
    assert task.progress == 50


@respx.mock
def test_wait_for_task_already_completed():
    respx.get("/api/task/task-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "task-1",
                "type": "デプロイ",
                "object_uuid": "vm-1",
                "object_name": "test-vm",
                "start_datetime": "2026-04-14 16:34:13",
                "end_datetime": "2026-04-14 16:40:00",
                "status": "Completed",
                "progress": 100,
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    task = wait_for_task(client, "task-1", poll_interval=0, timeout=5)
    assert task.status.value == "Completed"


@respx.mock
def test_wait_for_task_polls_until_done():
    route = respx.get("/api/task/task-1/")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "uuid": "task-1",
                "type": "デプロイ",
                "object_uuid": "vm-1",
                "object_name": "test-vm",
                "start_datetime": "2026-04-14 16:34:13",
                "end_datetime": None,
                "status": "Running",
                "progress": 50,
            },
        ),
        httpx.Response(
            200,
            json={
                "uuid": "task-1",
                "type": "デプロイ",
                "object_uuid": "vm-1",
                "object_name": "test-vm",
                "start_datetime": "2026-04-14 16:34:13",
                "end_datetime": "2026-04-14 16:40:00",
                "status": "Completed",
                "progress": 100,
            },
        ),
    ]
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    task = wait_for_task(client, "task-1", poll_interval=0, timeout=5)
    assert task.status.value == "Completed"
    assert route.call_count == 2
