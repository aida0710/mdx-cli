from unittest.mock import patch

import pytest
import typer

from mdx_cli.commands._common import (
    is_uuid,
    prompt_int,
    resolve_project_id,
    select_from_list,
)


def test_resolve_project_id_with_direct_arg():
    """直接引数が渡された場合はそれを返す"""
    result = resolve_project_id("proj-direct")
    assert result == "proj-direct"


def test_resolve_project_id_with_saved_project():
    """引数がなく保存済みプロジェクトIDがある場合はそれを返す"""
    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        mock_get_store.return_value.load_project_id.return_value = "proj-saved"
        result = resolve_project_id(None)
        assert result == "proj-saved"


def test_resolve_project_id_with_nothing_raises():
    """引数も保存済みIDもない場合はBadParameterを送出する"""
    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        mock_get_store.return_value.load_project_id.return_value = None
        with pytest.raises(typer.BadParameter):
            resolve_project_id(None)


# --- is_uuid ---


def test_is_uuid_accepts_canonical_uuid():
    assert is_uuid("00000000-0000-0000-0000-000000000001")
    assert is_uuid("A1B2C3D4-E5F6-7890-ABCD-EF0123456789")


def test_is_uuid_rejects_vm_names():
    """36文字でハイフンを含むVM名を誤判定しない"""
    assert not is_uuid("my-very-long-virtual-machine-name-01")  # 36文字
    assert not is_uuid("crawler-a-0")
    assert not is_uuid("")


# --- prompt_int ---


def test_prompt_int_valid_input(mocker):
    """有効な数値が入力された場合はその値を返す"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.return_value = "3"
    assert prompt_int("番号を入力:") == 3


def test_prompt_int_with_max_val(mocker):
    """max_val内の有効な数値を受け付ける"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.return_value = "2"
    assert prompt_int("番号を入力:", max_val=5) == 2


def test_prompt_int_invalid_then_valid(mocker):
    """無効な入力の後に有効な入力があればその値を返す"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.side_effect = ["abc", "2"]
    assert prompt_int("番号を入力:") == 2
    assert mock_q.text.return_value.unsafe_ask.call_count == 2


def test_prompt_int_out_of_range_then_valid(mocker):
    """範囲外の入力の後に範囲内の入力があればその値を返す"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.side_effect = ["10", "3"]
    assert prompt_int("番号を入力:", max_val=5) == 3
    assert mock_q.text.return_value.unsafe_ask.call_count == 2


def test_prompt_int_rejects_zero_and_negative(mocker):
    """0 や負数は拒否してリトライする（idx=-1 で末尾要素を選ぶバグの防止）"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.side_effect = ["0", "-1", "1"]
    assert prompt_int("番号を入力:", max_val=5) == 1
    assert mock_q.text.return_value.unsafe_ask.call_count == 3


def test_prompt_int_uses_default(mocker):
    """default はそのまま questionary.text に渡される"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.return_value = "4"
    assert prompt_int("番号を入力:", max_val=5, default="4") == 4
    assert mock_q.text.call_args.kwargs["default"] == "4"


# --- select_from_list ---


def test_select_from_list_returns_selected_item(mocker):
    """番号入力で対応する要素を返す（1始まり）"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.return_value = "2"
    items = ["alpha", "beta", "gamma"]
    result = select_from_list(items, lambda x: x, title="候補:")
    assert result == "beta"


def test_select_from_list_retries_on_invalid_number(mocker):
    """0・範囲外・非数値はリトライし、有効な番号で選択する"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.side_effect = ["0", "9", "x", "3"]
    items = ["alpha", "beta", "gamma"]
    result = select_from_list(items, lambda x: x)
    assert result == "gamma"


def test_select_from_list_empty_items_raises():
    """空リストは ValueError（呼び出し側が先に空チェックする契約）"""
    with pytest.raises(ValueError):
        select_from_list([], lambda x: x)


def test_select_from_list_displays_formatted_items(mocker, capsys):
    """formatter の結果が番号付きで表示される"""
    mock_q = mocker.patch("mdx_cli.commands._common.questionary")
    mock_q.text.return_value.unsafe_ask.return_value = "1"
    select_from_list(["vm-a"], lambda x: f"{x} [PowerON]", title="VM一覧:")
    out = capsys.readouterr().out
    assert "VM一覧:" in out
    assert "1) vm-a [PowerON]" in out


# --- get_client: 期限が近いトークンの事前リフレッシュ ---


def test_get_client_refreshes_token_if_near_expiry():
    """トークンの期限が近ければ自動リフレッシュして新トークンを使う。"""
    from mdx_cli.commands._common import get_client

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = "old-jwt"
        with patch("mdx_cli.commands._common.token_needs_refresh", return_value=True):
            with patch("mdx_cli.commands._common.refresh_saved_token", return_value="new-jwt") as mock_refresh:
                with patch("mdx_cli.commands._common.create_client") as mock_create:
                    get_client()
                    mock_refresh.assert_called_once()
                    # create_client は新トークンで呼ばれる
                    mock_create.assert_called_once()
                    assert mock_create.call_args.kwargs["token"] == "new-jwt"


def test_get_client_skips_refresh_if_token_valid():
    """トークンがまだ有効ならリフレッシュしない。"""
    from mdx_cli.commands._common import get_client

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = "valid-jwt"
        with patch("mdx_cli.commands._common.token_needs_refresh", return_value=False):
            with patch("mdx_cli.commands._common.refresh_saved_token") as mock_refresh:
                with patch("mdx_cli.commands._common.create_client") as mock_create:
                    get_client()
                    mock_refresh.assert_not_called()
                    assert mock_create.call_args.kwargs["token"] == "valid-jwt"


def test_get_client_no_token_skips_refresh():
    """トークン未保存時はリフレッシュしない。"""
    from mdx_cli.commands._common import get_client

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = None
        with patch("mdx_cli.commands._common.refresh_saved_token") as mock_refresh:
            with patch("mdx_cli.commands._common.create_client") as mock_create:
                get_client()
                mock_refresh.assert_not_called()
                assert mock_create.call_args.kwargs["token"] is None


def test_get_client_uses_old_token_if_refresh_fails():
    """リフレッシュ失敗時は既存トークンで続行（MDXAuthの401対応が保険）。"""
    from mdx_cli.commands._common import get_client

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = "stale-jwt"
        with patch("mdx_cli.commands._common.token_needs_refresh", return_value=True):
            with patch("mdx_cli.commands._common.refresh_saved_token", return_value=None):
                with patch("mdx_cli.commands._common.create_client") as mock_create:
                    get_client()
                    assert mock_create.call_args.kwargs["token"] == "stale-jwt"


# --- 並列API用の認証コンテキスト ---


def test_get_auth_context_returns_token_and_base_url():
    """保存済みトークンとベースURLを返す。"""
    from mdx_cli.commands._common import get_auth_context

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        mock_get_store.return_value.load_token.return_value = "jwt-123"
        token, base_url = get_auth_context()
        assert token == "jwt-123"
        assert base_url.startswith("https://")


def test_get_auth_context_empty_token_when_not_logged_in():
    """トークン未保存時は空文字を返す。"""
    from mdx_cli.commands._common import get_auth_context

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        mock_get_store.return_value.load_token.return_value = None
        token, _ = get_auth_context()
        assert token == ""


def test_refresh_token_proactive_saves_new_token():
    """リフレッシュ成功時は新トークンを保存する。"""
    from mdx_cli.commands._common import refresh_token_proactive

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = "old-token"
        with patch("mdx_cli.commands._common.refresh_saved_token", return_value="new-token"):
            refresh_token_proactive()
            store.save_token.assert_called_once_with("new-token")


def test_refresh_token_proactive_no_token_does_nothing():
    """トークン未保存なら何もしない。"""
    from mdx_cli.commands._common import refresh_token_proactive

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = None
        refresh_token_proactive()
        store.save_token.assert_not_called()


def test_refresh_token_proactive_failure_keeps_old_token():
    """リフレッシュ失敗時も例外を投げず既存トークンを保持する。"""
    from mdx_cli.commands._common import refresh_token_proactive

    with patch("mdx_cli.commands._common.get_store") as mock_get_store:
        store = mock_get_store.return_value
        store.load_token.return_value = "old-token"
        with patch("mdx_cli.commands._common.refresh_saved_token", return_value=None):
            refresh_token_proactive()
            store.save_token.assert_not_called()
