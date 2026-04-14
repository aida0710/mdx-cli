import httpx
import respx

from mdx_cli.api.endpoints.tasks import list_history
from mdx_cli.models.history import HistoryEntry


def _make_entry(i: int) -> dict:
    return {
        "type": "デプロイ",
        "start_datetime": f"2026-04-{i:02d} 10:00:00",
        "end_datetime": f"2026-04-{i:02d} 10:10:00",
        "status": "Completed",
        "user_name": "testuser",
        "object_name": f"vm-{i}",
    }


@respx.mock
def test_list_history_basic():
    """基本的な履歴一覧を取得できる"""
    respx.get("/api/history/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "previous": None,
                "results": [_make_entry(1), _make_entry(2)],
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    entries = list_history(client, "proj-1", limit=10)
    assert len(entries) == 2
    assert all(isinstance(e, HistoryEntry) for e in entries)
    assert entries[0].object_name == "vm-1"
    assert entries[1].object_name == "vm-2"


@respx.mock
def test_list_history_type_filter_passed():
    """type_filterパラメータがリクエストに含まれる"""
    route = respx.get("/api/history/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json={"count": 1, "next": None, "previous": None, "results": [_make_entry(1)]},
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    entries = list_history(client, "proj-1", limit=10, type_filter="デプロイ")
    assert len(entries) == 1
    # typeパラメータがリクエストに含まれていることを確認
    called_request = route.calls[0].request
    assert "type=%E3%83%87%E3%83%97%E3%83%AD%E3%82%A4" in str(called_request.url)


@respx.mock
def test_list_history_stops_at_limit():
    """limitを超えて取得しない"""
    respx.get("/api/history/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 5,
                "next": None,
                "previous": None,
                "results": [_make_entry(i) for i in range(1, 6)],
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    entries = list_history(client, "proj-1", limit=3)
    assert len(entries) == 3


@respx.mock
def test_list_history_list_response():
    """リスト形式（非ページネーション）のレスポンスも処理できる"""
    respx.get("/api/history/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json=[_make_entry(1), _make_entry(2), _make_entry(3)],
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    entries = list_history(client, "proj-1", limit=10)
    assert len(entries) == 3
    assert all(isinstance(e, HistoryEntry) for e in entries)
