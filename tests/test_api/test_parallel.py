from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest
import respx

from mdx_cli.api.parallel import parallel_get


@respx.mock
def test_parallel_get_fetches_multiple_urls():
    """parallel_getが複数のURLを並列取得してレスポンスのリストを返す"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-1", "name": "VM One"})
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-2/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-2", "name": "VM Two"})
    )
    results = parallel_get(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/", "/api/vm/vm-2/"],
    )
    assert len(results) == 2
    uuids = {r["uuid"] for r in results}
    assert uuids == {"vm-1", "vm-2"}


@respx.mock
def test_parallel_get_empty_paths():
    """pathsが空リストの場合は空リストを返す"""
    results = parallel_get(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=[],
    )
    assert results == []


@respx.mock
def test_parallel_get_on_progress_callback_called():
    """on_progressコールバックが各URLの完了時に呼ばれる"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-1"})
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-2/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-2"})
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-3/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-3"})
    )

    called_indices = []

    def on_progress(index: int) -> None:
        called_indices.append(index)

    results = parallel_get(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/", "/api/vm/vm-2/", "/api/vm/vm-3/"],
        on_progress=on_progress,
    )
    assert len(results) == 3
    assert len(called_indices) == 3
    assert sorted(called_indices) == [0, 1, 2]


@respx.mock
def test_parallel_get_preserves_order():
    """parallel_getはpathsと同じ順序でレスポンスを返す"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-1"})
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-2/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-2"})
    )
    results = parallel_get(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/", "/api/vm/vm-2/"],
    )
    assert results[0]["uuid"] == "vm-1"
    assert results[1]["uuid"] == "vm-2"
