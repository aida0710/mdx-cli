"""並列APIユーティリティ

httpx.AsyncClient + asyncio.Semaphore で同時実行数を制限しつつ並列実行。
GET / POST / タスク待機に対応。
"""

import asyncio
from typing import Callable

import httpx
from mdx_cli.settings import Settings

MAX_CONCURRENT = 50


def _make_async_client(base_url: str, token: str, timeout: int) -> httpx.AsyncClient:
    resolved_base = base_url if base_url.endswith("/") else base_url + "/"
    return httpx.AsyncClient(
        base_url=resolved_base,
        timeout=timeout,
        headers={"Authorization": f"JWT {token}"},
    )


# --- GET ---

async def _fetch_one(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    index: int,
    on_progress: Callable[[int], None] | None,
) -> dict:
    async with semaphore:
        resp = await client.get(url)
        resp.raise_for_status()
        if on_progress:
            on_progress(index)
        return resp.json()


def parallel_get(
    base_url: str,
    token: str,
    paths: list[str],
    max_concurrent: int = MAX_CONCURRENT,
    on_progress: Callable[[int], None] | None = None,
) -> list[dict]:
    """複数のGET APIを並列に取得する。"""
    settings = Settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _fetch_one(client, path, semaphore, i, on_progress)
                for i, path in enumerate(paths)
            ]
            return await asyncio.gather(*tasks)

    return list(asyncio.run(_run()))


# --- POST ---

async def _post_one(
    client: httpx.AsyncClient,
    path: str,
    json_body: dict | None,
    semaphore: asyncio.Semaphore,
    index: int,
    on_progress: Callable[[int], None] | None,
) -> dict:
    async with semaphore:
        resp = await client.post(path, json=json_body)
        resp.raise_for_status()
        if on_progress:
            on_progress(index)
        try:
            return resp.json()
        except Exception:
            return {}


def parallel_post(
    base_url: str,
    token: str,
    requests: list[dict],
    max_concurrent: int = MAX_CONCURRENT,
    on_progress: Callable[[int], None] | None = None,
) -> list[dict]:
    """複数のPOST APIを並列に実行する。

    Args:
        requests: [{"path": "/api/...", "json": {...}}, ...] のリスト
    """
    settings = Settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _post_one(client, r["path"], r.get("json"), semaphore, i, on_progress)
                for i, r in enumerate(requests)
            ]
            return await asyncio.gather(*tasks)

    return list(asyncio.run(_run()))


# --- タスク待機 ---

async def _wait_one(
    client: httpx.AsyncClient,
    task_id: str,
    semaphore: asyncio.Semaphore,
    poll_interval: int,
    timeout: int,
    on_done: Callable[[str, dict], None] | None,
) -> dict:
    async with semaphore:
        import time
        start = time.monotonic()
        while True:
            resp = await client.get(f"/api/task/{task_id}/")
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status in ("Completed", "Failed"):
                if on_done:
                    on_done(task_id, data)
                return data
            if time.monotonic() - start >= timeout:
                if on_done:
                    on_done(task_id, data)
                return data
            await asyncio.sleep(poll_interval)


def parallel_wait(
    base_url: str,
    token: str,
    task_ids: list[str],
    poll_interval: int = 3,
    timeout: int = 600,
    max_concurrent: int = MAX_CONCURRENT,
    on_done: Callable[[str, dict], None] | None = None,
) -> list[dict]:
    """複数タスクを並列でポーリングし全完了まで待機する。

    Args:
        on_done: 各タスク完了時に (task_id, task_data) で呼ばれるコールバック
    """
    settings = Settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _wait_one(client, tid, semaphore, poll_interval, timeout, on_done)
                for tid in task_ids
            ]
            return await asyncio.gather(*tasks)

    return list(asyncio.run(_run()))
