from mdx_cli.models.history import HistoryEntry


def test_history_entry_from_api_response():
    """実際のAPIレスポンス形式でHistoryEntryを作成できる"""
    data = {
        "type": "デプロイ",
        "start_datetime": "2026-04-14 16:34:13",
        "end_datetime": "2026-04-14 16:40:00",
        "status": "Completed",
        "user_name": "testuser",
        "object_name": "my-vm",
    }
    entry = HistoryEntry.model_validate(data)
    assert entry.type == "デプロイ"
    assert entry.start_datetime == "2026-04-14 16:34:13"
    assert entry.end_datetime == "2026-04-14 16:40:00"
    assert entry.status == "Completed"
    assert entry.user_name == "testuser"
    assert entry.object_name == "my-vm"


def test_history_entry_all_fields_default_to_empty_string():
    """全フィールドが空文字にデフォルトする"""
    entry = HistoryEntry.model_validate({})
    assert entry.type == ""
    assert entry.start_datetime == ""
    assert entry.end_datetime == ""
    assert entry.status == ""
    assert entry.user_name == ""
    assert entry.object_name == ""


def test_history_entry_partial_fields():
    """一部フィールドのみ指定した場合、残りは空文字"""
    data = {
        "type": "停止",
        "status": "Running",
    }
    entry = HistoryEntry.model_validate(data)
    assert entry.type == "停止"
    assert entry.status == "Running"
    assert entry.start_datetime == ""
    assert entry.user_name == ""


def test_history_entry_extra_fields_allowed():
    """未知フィールドがあってもエラーにならない（extra='allow'）"""
    data = {
        "type": "デプロイ",
        "status": "Completed",
        "unknown_field": "some_value",
        "extra_data": {"nested": True},
    }
    entry = HistoryEntry.model_validate(data)
    assert entry.type == "デプロイ"
    assert entry.status == "Completed"
