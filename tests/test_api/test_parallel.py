from unittest.mock import patch

import httpx
import pytest
import respx

from mdx_cli.api.parallel import parallel_get, parallel_poll, parallel_wait


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


@respx.mock
def test_parallel_get_404_is_retried():
    """404 もリトライ対象（サーバー負荷時の一時エラーとして扱う）。"""
    # 1回目404 → 2回目200で成功
    respx.get("https://oprpl.mdx.jp/api/vm/vm-flaky/").mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(200, json={"uuid": "vm-flaky"}),
        ]
    )
    # RETRY_BACKOFFを短くしてテストを速く
    with patch("mdx_cli.api.parallel.RETRY_BACKOFF", [0, 0, 0]):
        results = parallel_get(
            base_url="https://oprpl.mdx.jp",
            token="test-token",
            paths=["/api/vm/vm-flaky/"],
        )
    assert results[0]["uuid"] == "vm-flaky"


@respx.mock
def test_parallel_get_timeout_is_retried():
    """ReadTimeout もリトライ対象（並列負荷時のタイムアウトを一時エラーとして扱う）。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-slow/").mock(
        side_effect=[
            httpx.ReadTimeout("timeout"),
            httpx.Response(200, json={"uuid": "vm-slow"}),
        ]
    )
    with patch("mdx_cli.api.parallel.RETRY_BACKOFF", [0, 0, 0]):
        results = parallel_get(
            base_url="https://oprpl.mdx.jp",
            token="test-token",
            paths=["/api/vm/vm-slow/"],
        )
    assert results[0]["uuid"] == "vm-slow"


@respx.mock
def test_parallel_get_return_exceptions_partial_failure():
    """return_exceptions=True で部分失敗があっても全体は止まらない。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-1"})
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-bad/").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-2/").mock(
        return_value=httpx.Response(200, json={"uuid": "vm-2"})
    )
    with patch("mdx_cli.api.parallel.RETRY_BACKOFF", [0, 0, 0]):
        results = parallel_get(
            base_url="https://oprpl.mdx.jp",
            token="test-token",
            paths=["/api/vm/vm-1/", "/api/vm/vm-bad/", "/api/vm/vm-2/"],
            return_exceptions=True,
        )
    assert len(results) == 3
    assert results[0]["uuid"] == "vm-1"
    assert isinstance(results[1], httpx.HTTPStatusError)
    assert results[2]["uuid"] == "vm-2"


@respx.mock
def test_parallel_get_default_raises_on_persistent_failure():
    """return_exceptions=False（デフォルト）なら例外がraiseされる。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-bad/").mock(
        return_value=httpx.Response(500)
    )
    with patch("mdx_cli.api.parallel.RETRY_BACKOFF", [0, 0, 0]):
        with pytest.raises(httpx.HTTPStatusError):
            parallel_get(
                base_url="https://oprpl.mdx.jp",
                token="test-token",
                paths=["/api/vm/vm-bad/"],
            )


@respx.mock
def test_parallel_wait_retries_on_404():
    """初回 404 でもリトライして最終的に成功すれば結果を返す。

    deploy 直後の task_id は サーバー側の登録が遅延して 404 になることがある。
    並行プロセスが refresh するとさらに発生しやすい。
    """
    respx.get("https://oprpl.mdx.jp/api/task/task-1/").mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(404),
            httpx.Response(200, json={"status": "Completed", "object_name": "vm-1"}),
        ]
    )
    results = parallel_wait(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        task_ids=["task-1"],
        poll_interval=0,
        timeout=10,
    )
    assert len(results) == 1
    assert results[0]["status"] == "Completed"


@respx.mock
def test_parallel_wait_retries_on_timeout():
    """タスク待機中の ReadTimeout もリトライして継続する。"""
    respx.get("https://oprpl.mdx.jp/api/task/task-slow/").mock(
        side_effect=[
            httpx.ReadTimeout("timeout"),
            httpx.Response(200, json={"status": "Completed"}),
        ]
    )
    results = parallel_wait(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        task_ids=["task-slow"],
        poll_interval=0,
        timeout=10,
    )
    assert len(results) == 1
    assert results[0]["status"] == "Completed"


@respx.mock
def test_parallel_wait_404_eventually_returns_unknown():
    """404 が一定回数続いたら諦めてエラーなく抜ける（無限ループ防止）。"""
    respx.get("https://oprpl.mdx.jp/api/task/task-bad/").mock(
        return_value=httpx.Response(404)
    )
    results = parallel_wait(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        task_ids=["task-bad"],
        poll_interval=0,
        timeout=1,
    )
    # エラーなく結果が返る（status は不明）
    assert len(results) == 1


# --- parallel_poll ---


@respx.mock
def test_parallel_poll_returns_true_when_condition_met():
    """初回レスポンスで条件成立なら True を返す。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"status": "PowerOFF"})
    )
    results = parallel_poll(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/"],
        is_done=lambda data: data.get("status") != "PowerON",
        poll_interval=0,
        max_polls=3,
    )
    assert results == [True]


@respx.mock
def test_parallel_poll_polls_until_condition():
    """条件成立までポーリングを繰り返す。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        side_effect=[
            httpx.Response(200, json={"status": "PowerON"}),
            httpx.Response(200, json={"status": "PowerON"}),
            httpx.Response(200, json={"status": "PowerOFF"}),
        ]
    )
    results = parallel_poll(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/"],
        is_done=lambda data: data.get("status") != "PowerON",
        poll_interval=0,
        max_polls=5,
    )
    assert results == [True]


@respx.mock
def test_parallel_poll_returns_false_after_max_polls():
    """max_polls までに条件が成立しなければ False。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"status": "PowerON"})
    )
    results = parallel_poll(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/"],
        is_done=lambda data: data.get("status") != "PowerON",
        poll_interval=0,
        max_polls=2,
    )
    assert results == [False]


@respx.mock
def test_parallel_poll_survives_non_json_response():
    """502エラーページや空ボディはクラッシュせず次の周期で再確認する。

    70台 destroy の停止待ち中にサーバーが非JSONレスポンスを返し、
    JSONDecodeError でコマンド全体が落ちたバグの回帰テスト。
    """
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        side_effect=[
            httpx.Response(502, text="<html>Bad Gateway</html>"),
            httpx.Response(200, content=b""),
            httpx.Response(200, json={"status": "PowerOFF"}),
        ]
    )
    results = parallel_poll(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/"],
        is_done=lambda data: data.get("status") != "PowerON",
        poll_interval=0,
        max_polls=5,
    )
    assert results == [True]


@respx.mock
def test_parallel_poll_survives_network_errors():
    """接続エラー・タイムアウトもクラッシュせずポーリングを継続する。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        side_effect=[
            httpx.ReadTimeout("timeout"),
            httpx.ConnectError("connection failed"),
            httpx.Response(200, json={"status": "PowerOFF"}),
        ]
    )
    results = parallel_poll(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/"],
        is_done=lambda data: data.get("status") != "PowerON",
        poll_interval=0,
        max_polls=5,
    )
    assert results == [True]


@respx.mock
def test_parallel_poll_on_done_called_with_index():
    """条件成立時に on_done が paths のインデックスで呼ばれる。"""
    respx.get("https://oprpl.mdx.jp/api/vm/vm-1/").mock(
        return_value=httpx.Response(200, json={"status": "PowerOFF"})
    )
    respx.get("https://oprpl.mdx.jp/api/vm/vm-2/").mock(
        return_value=httpx.Response(200, json={"status": "PowerOFF"})
    )
    called: list[int] = []
    parallel_poll(
        base_url="https://oprpl.mdx.jp",
        token="test-token",
        paths=["/api/vm/vm-1/", "/api/vm/vm-2/"],
        is_done=lambda data: data.get("status") != "PowerON",
        poll_interval=0,
        max_polls=3,
        on_done=called.append,
    )
    assert sorted(called) == [0, 1]
