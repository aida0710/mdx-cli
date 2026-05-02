import sys
from unittest.mock import patch, MagicMock

import pytest
import typer

from mdx_cli.commands._common import resolve_project_id, prompt_int


def test_resolve_project_id_with_direct_arg():
    """直接引数が渡された場合はそれを返す"""
    result = resolve_project_id("proj-direct")
    assert result == "proj-direct"


def test_resolve_project_id_with_saved_project(tmp_path, monkeypatch):
    """引数がなく保存済みプロジェクトIDがある場合はそれを返す"""
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands._common.CredentialStore") as MockStore:
        store = MockStore.return_value
        store.load_project_id.return_value = "proj-saved"
        result = resolve_project_id(None)
        assert result == "proj-saved"


def test_resolve_project_id_with_nothing_raises(tmp_path, monkeypatch):
    """引数も保存済みIDもない場合はBadParameterを送出する"""
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands._common.CredentialStore") as MockStore:
        store = MockStore.return_value
        store.load_project_id.return_value = None
        with pytest.raises(typer.BadParameter):
            resolve_project_id(None)


def _mock_questionary(mocker):
    """questinaryのモックをsys.modulesに注入して返す。

    prompt_int内でlocalにimportされるため、sys.modulesへの注入が必要。
    """
    mock_q = MagicMock()
    mocker.patch.dict(sys.modules, {"questionary": mock_q})
    return mock_q


def test_prompt_int_valid_input(mocker):
    """有効な数値が入力された場合はその値を返す"""
    mock_q = _mock_questionary(mocker)
    mock_q.text.return_value.unsafe_ask.return_value = "3"
    result = prompt_int("番号を入力:")
    assert result == 3


def test_prompt_int_with_max_val(mocker):
    """max_val内の有効な数値を受け付ける"""
    mock_q = _mock_questionary(mocker)
    mock_q.text.return_value.unsafe_ask.return_value = "2"
    result = prompt_int("番号を入力:", max_val=5)
    assert result == 2


def test_prompt_int_invalid_then_valid(mocker):
    """無効な入力の後に有効な入力があればその値を返す"""
    mock_q = _mock_questionary(mocker)
    mock_q.text.return_value.unsafe_ask.side_effect = ["abc", "2"]
    result = prompt_int("番号を入力:")
    assert result == 2
    assert mock_q.text.return_value.unsafe_ask.call_count == 2


def test_prompt_int_out_of_range_then_valid(mocker):
    """範囲外の入力の後に範囲内の入力があればその値を返す"""
    mock_q = _mock_questionary(mocker)
    mock_q.text.return_value.unsafe_ask.side_effect = ["10", "3"]
    result = prompt_int("番号を入力:", max_val=5)
    assert result == 3
    assert mock_q.text.return_value.unsafe_ask.call_count == 2


# --- get_client: 期限が近いトークンの事前リフレッシュ ---


def test_get_client_refreshes_token_if_near_expiry():
    """トークンの期限が近ければ自動リフレッシュして新トークンを使う。"""
    from mdx_cli.commands._common import get_client

    with patch("mdx_cli.commands._common.CredentialStore") as MockStore:
        store = MockStore.return_value
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

    with patch("mdx_cli.commands._common.CredentialStore") as MockStore:
        store = MockStore.return_value
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

    with patch("mdx_cli.commands._common.CredentialStore") as MockStore:
        store = MockStore.return_value
        store.load_token.return_value = None
        with patch("mdx_cli.commands._common.refresh_saved_token") as mock_refresh:
            with patch("mdx_cli.commands._common.create_client") as mock_create:
                get_client()
                mock_refresh.assert_not_called()
                assert mock_create.call_args.kwargs["token"] is None


def test_get_client_uses_old_token_if_refresh_fails():
    """リフレッシュ失敗時は既存トークンで続行（MDXAuthの401対応が保険）。"""
    from mdx_cli.commands._common import get_client

    with patch("mdx_cli.commands._common.CredentialStore") as MockStore:
        store = MockStore.return_value
        store.load_token.return_value = "stale-jwt"
        with patch("mdx_cli.commands._common.token_needs_refresh", return_value=True):
            with patch("mdx_cli.commands._common.refresh_saved_token", return_value=None):
                with patch("mdx_cli.commands._common.create_client") as mock_create:
                    get_client()
                    assert mock_create.call_args.kwargs["token"] == "stale-jwt"
