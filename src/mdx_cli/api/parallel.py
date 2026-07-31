"""並列APIユーティリティ

httpx.AsyncClient + asyncio.Semaphore で同時実行数を制限しつつ並列実行。
GET / POST / タスク待機に対応。リトライ付き。
"""

import asyncio
import logging
import time
from typing import Callable

import httpx
from mdx_cli.settings import get_settings

logger = logging.getLogger("mdx_cli")

MAX_CONCURRENT_GET = 30
# /api/vm/{uuid}/ は応答が遅く、高並列にするとタイムアウトと再試行が増える。
MAX_CONCURRENT_VM_DETAIL = 8
# /api/vm/{uuid}/csv/ は軽量なので高並列で取り切れる。
MAX_CONCURRENT_CSV = 50
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
    """1つのGETを実行する（リトライ付き）。

    404 もリトライ対象。サーバー負荷時は一覧に存在するリソースの詳細が
    一時的に 404 で返ることがあるため、確定エラーとして扱わない。
    """
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                if on_progress:
                    on_progress(index)
                return resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
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
    return_exceptions: bool = False,
) -> list[dict]:
    """複数のGET APIを並列に取得する。

    return_exceptions=True にすると、失敗したリクエストはExceptionオブジェクトとして
    結果に含まれ、全体は止まらない（caller側で例外処理する）。
    """
    settings = get_settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _fetch_one(client, path, semaphore, i, on_progress)
                for i, path in enumerate(paths)
            ]
            return await asyncio.gather(*tasks, return_exceptions=return_exceptions)

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
            # TimeoutException は意図的にリトライしない: タイムアウトした
            # POSTはサーバー側で処理済みの可能性があり、再送すると
            # 電源操作・デプロイ等が二重実行されるリスクがあるため。
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
    settings = get_settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _post_one(client, r["path"], r.get("json"), semaphore, i, on_progress)
                for i, r in enumerate(requests)
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

    return list(asyncio.run(_run()))


# --- 条件ポーリング ---

async def _poll_one(
    client: httpx.AsyncClient,
    path: str,
    semaphore: asyncio.Semaphore,
    is_done: Callable[[dict], bool],
    poll_interval: int,
    max_polls: int,
    index: int,
    on_done: Callable[[int], None] | None,
) -> bool:
    """1つのパスをポーリングして is_done(json) が True になるまで待つ。

    一時エラー（5xx・負荷時の404・非JSONボディ・接続エラー・タイムアウト）は
    その周期を諦めて次の周期で再確認する（クラッシュさせない）。
    セマフォはリクエスト中のみ保持し、sleep中は解放する。遅いエンドポイントに
    同時リクエストが集中するのを防ぎつつ、他パスのポーリング周期は止めない。
    """
    for _ in range(max_polls):
        try:
            async with semaphore:
                resp = await client.get(path)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException, ValueError) as e:
            # ValueError は非JSONボディ（JSONDecodeError）を含む
            logger.debug("poll %s failed (%s), retry", path, e)
            await asyncio.sleep(poll_interval)
            continue
        if is_done(data):
            if on_done:
                on_done(index)
            return True
        await asyncio.sleep(poll_interval)
    return False


def parallel_poll(
    base_url: str,
    token: str,
    paths: list[str],
    is_done: Callable[[dict], bool],
    poll_interval: int = 5,
    max_polls: int = 60,
    max_concurrent: int = MAX_CONCURRENT_GET,
    on_done: Callable[[int], None] | None = None,
) -> list[bool]:
    """複数パスを並列ポーリングし、各レスポンスJSONが is_done を満たすまで待つ。

    戻り値: paths と同順の bool リスト（True=条件成立、False=max_polls超過）。
    """
    settings = get_settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _poll_one(client, path, semaphore, is_done, poll_interval, max_polls, i, on_done)
                for i, path in enumerate(paths)
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
    """1つのタスクをポーリングして完了を待つ。

    deploy 直後の task_id はサーバー側登録の遅延で 404 を返すことがある
    （並行プロセスが refresh するとさらに発生しやすい）。
    404 は一時エラーとして扱い、リトライを続ける（タイムアウトで諦める）。

    セマフォはリクエスト中のみ保持し、sleep中は解放する（_poll_one と同じ）。
    ループ全体で保持すると max_concurrent を超えた分のタスクが先行タスクの
    完了までポーリングを開始できず、待機がシリアル化する。
    """
    start = time.monotonic()
    last_data: dict = {}
    while True:
        try:
            async with semaphore:
                resp = await client.get(f"/api/task/{task_id}/")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            # ネットワーク一時エラー → タイムアウトまでポーリングを継続
            if time.monotonic() - start >= timeout:
                if on_done:
                    on_done(task_id, last_data)
                return last_data
            logger.debug("task %s poll failed (%s), retry", task_id, e)
            await asyncio.sleep(poll_interval)
            continue
        if resp.status_code == 404:
            # タスクがまだ登録されてない or トークン競合 → リトライ
            if time.monotonic() - start >= timeout:
                if on_done:
                    on_done(task_id, last_data)
                return last_data
            await asyncio.sleep(poll_interval)
            continue
        resp.raise_for_status()
        data = resp.json()
        last_data = data
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
    settings = get_settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        async with _make_async_client(base_url, token, settings.request_timeout) as client:
            tasks = [
                _wait_one(client, tid, semaphore, poll_interval, timeout, on_done)
                for tid in task_ids
            ]
            return await asyncio.gather(*tasks)

    return list(asyncio.run(_run()))
