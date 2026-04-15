"""並列APIユーティリティ

httpx.AsyncClient + asyncio.Semaphore で同時実行数を制限しつつ並列実行。
GET / POST / タスク待機に対応。リトライ付き。
"""

import asyncio
import logging
from typing import Callable

import httpx
from mdx_cli.settings import Settings

logger = logging.getLogger("mdx_cli")

MAX_CONCURRENT_GET = 50
MAX_CONCURRENT_POST = 5
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # 秒


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
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                if on_progress:
                    on_progress(index)
                return resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF[attempt]
                    logger.debug("GET %s failed (%s), retry in %ds", url, e, wait)
                    await asyncio.sleep(wait)
                else:
                    raise


def parallel_get(
    base_url: str,
    token: str,
    paths: list[str],
    max_concurrent: int = MAX_CONCURRENT_GET,
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
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(path, json=json_body)
                resp.raise_for_status()
                if on_progress:
                    on_progress(index)
                try:
                    return resp.json()
                except Exception:
                    return {}
            except (httpx.HTTPStatusError, httpx.ConnectError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF[attempt]
                    logger.debug("POST %s failed (%s), retry in %ds", path, e, wait)
                    await asyncio.sleep(wait)
                else:
                    raise


def parallel_post(
    base_url: str,
    token: str,
    requests: list[dict],
    max_concurrent: int = MAX_CONCURRENT_POST,
    on_progress: Callable[[int], None] | None = None,
) -> list[dict | Exception]:
    """複数のPOST APIを並列に実行する（リトライ付き）。

    失敗したリクエストはExceptionオブジェクトとして返る（全体は止まらない）。
    """
    settings = Settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _post_one(client, r["path"], r.get("json"), semaphore, i, on_progress)
                for i, r in enumerate(requests)
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

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
    max_concurrent: int = MAX_CONCURRENT_POST,
    on_done: Callable[[str, dict], None] | None = None,
) -> list[dict]:
    """複数タスクを並列でポーリングし全完了まで待機する。"""
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
