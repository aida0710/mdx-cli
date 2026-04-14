"""並列API取得ユーティリティ

httpx.AsyncClient + asyncio.Semaphore で同時実行数を制限しつつ並列取得。
進捗コールバック付き。
"""

import asyncio
from typing import Callable

import httpx
from mdx_cli.settings import Settings


async def _fetch_one(
    async_client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    index: int,
    on_progress: Callable[[int], None] | None,
) -> dict:
    async with semaphore:
        resp = await async_client.get(url)
        resp.raise_for_status()
        if on_progress:
            on_progress(index)
        return resp.json()


def parallel_get(
    base_url: str,
    token: str,
    paths: list[str],
    max_concurrent: int = 10,
    on_progress: Callable[[int], None] | None = None,
) -> list[dict]:
    """複数のGET APIを並列に取得する。

    Args:
        base_url: APIベースURL
        token: JWTトークン
        paths: 取得するAPIパスのリスト
        max_concurrent: 最大同時実行数
        on_progress: 1件完了ごとに呼ばれるコールバック（完了インデックスを渡す）

    Returns:
        pathsと同じ順序のレスポンスJSONリスト
    """
    settings = Settings()

    async def _run():
        semaphore = asyncio.Semaphore(max_concurrent)
        resolved_base = base_url if base_url.endswith("/") else base_url + "/"
        async with httpx.AsyncClient(
            base_url=resolved_base,
            timeout=settings.request_timeout,
            headers={
                "Authorization": f"JWT {token}",
            },
        ) as client:
            tasks = [
                _fetch_one(client, path, semaphore, i, on_progress)
                for i, path in enumerate(paths)
            ]
            return await asyncio.gather(*tasks)

    return list(asyncio.run(_run()))
