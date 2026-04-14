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
