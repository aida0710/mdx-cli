import time

import httpx

from mdx_cli.models.history import HistoryEntry
from mdx_cli.models.task import Task


def get_task(client: httpx.Client, task_id: str) -> Task:
    resp = client.get(f"/api/task/{task_id}/")
    resp.raise_for_status()
    return Task.model_validate(resp.json())


def wait_for_task(
    client: httpx.Client,
    task_id: str,
    poll_interval: int = 3,
    timeout: int = 600,
) -> Task:
    start = time.monotonic()
    while True:
        task = get_task(client, task_id)
        if task.is_terminal:
            return task
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            raise TimeoutError(
                f"タスク {task_id} がタイムアウトしました（{timeout}秒）"
            )
        time.sleep(poll_interval)


def list_history(
    client: httpx.Client,
    project_id: str,
    limit: int = 100,
    type_filter: str | None = None,
    ordering: str = "-start_datetime",
) -> list[HistoryEntry]:
    """操作履歴を取得する。ページネーションせず指定件数まで取得。"""
    params: dict = {
        "page_size": min(limit, 100),
        "ordering": ordering,
    }
    if type_filter:
        params["type"] = type_filter

    all_items: list[dict] = []
    page = 1
    while len(all_items) < limit:
        params["page"] = page
        resp = client.get(f"/api/history/project/{project_id}/", params=params)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            all_items.extend(data)
            break

        results = data.get("results", [])
        all_items.extend(results)

        if not data.get("next") or len(results) == 0:
            break
        page += 1

    return [HistoryEntry.model_validate(item) for item in all_items[:limit]]
