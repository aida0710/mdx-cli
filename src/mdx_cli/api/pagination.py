"""自動ページネーション

MDX APIのページネーションレスポンス（count/next/previous/results）を
自動的に辿って全結果を取得する。
"""

import logging

import httpx

logger = logging.getLogger("mdx_cli")

PAGE_SIZE = 100  # サーバーの上限


def fetch_all(
    client: httpx.Client,
    path: str,
    params: dict | None = None,
    *,
    page_size: int | None = PAGE_SIZE,
) -> list[dict]:
    """ページネーションを自動で辿って全結果を取得する。

    スピナーはクライアントの event_hooks で自動制御される。
    ページネーション進捗はクライアントのスピナーメッセージを更新して表示。
    """
    params = dict(params or {})
    if page_size is not None:
        params.setdefault("page_size", page_size)

    resp = client.get(path, params=params)
    resp.raise_for_status()
    data = resp.json()

    # リスト直接の場合
    if isinstance(data, list):
        return data

    # ページネーションなしの場合
    if "results" not in data:
        return [data]

    all_items = list(data["results"])
    total = data.get("count", len(all_items))

    # スピナーの進捗を更新（MDXClient 以外の素の httpx.Client でも動くように getattr）
    spinner = getattr(client, "spinner", None)

    page = 1
    while data.get("next"):
        page += 1
        if spinner:
            spinner.update(f"取得中... ({len(all_items)}/{total})")
        resp = client.get(path, params={**params, "page": page})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "results" in data:
            all_items.extend(data["results"])
        else:
            break

    return all_items
