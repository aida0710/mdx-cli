import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.acl import app
from mdx_cli.models.network import ACL

runner = CliRunner()

_ACL_FIELDS = {
    "uuid": "acl-1",
    "protocol": "TCP",
    "src_address": "0.0.0.0",
    "src_mask": "0",
    "src_port": "Any",
    "dst_address": "10.0.0.1",
    "dst_mask": "32",
    "dst_port": "22",
}


def _make_acl(**overrides):
    return ACL(**{**_ACL_FIELDS, **overrides})


# --- _acl_field_steps ---


def _run_acl_steps(fields: dict) -> dict:
    from mdx_cli.commands._prompt_steps import run_steps
    from mdx_cli.commands.acl import _acl_field_steps

    run_steps(_acl_field_steps(fields))
    return fields


def test_acl_field_steps_add_mode_defaults():
    """新規追加時はアドレス系の初期値を使い、入力値で上書きする"""
    from mdx_cli.commands.acl import _NEW_ACL_FIELDS

    with patch("mdx_cli.commands.acl.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "TCP"
        mock_q.text.return_value.unsafe_ask.side_effect = [
            "0.0.0.0", "0", "Any",  # src
            "10.0.0.1", "32", "22",  # dst
        ]
        fields = _run_acl_steps(dict(_NEW_ACL_FIELDS))

    assert fields == {
        "protocol": "TCP",
        "src_address": "0.0.0.0",
        "src_mask": "0",
        "src_port": "Any",
        "dst_address": "10.0.0.1",
        "dst_mask": "32",
        "dst_port": "22",
    }
    # 新規追加時のデフォルト値。API はマスクをプレフィックス長で受け取る
    text_defaults = [c.kwargs.get("default") for c in mock_q.text.call_args_list]
    assert text_defaults == ["0.0.0.0", "0", "Any", "", "32", "Any"]


def test_acl_field_steps_edit_mode_uses_current_values_as_defaults():
    """編集時は既存ACLの現在値をデフォルトにする"""
    current = {key: value for key, value in _ACL_FIELDS.items() if key != "uuid"}
    with patch("mdx_cli.commands.acl.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "UDP"
        mock_q.text.return_value.unsafe_ask.side_effect = [
            "0.0.0.0", "0", "Any",
            "10.0.0.1", "32", "80",
        ]
        fields = _run_acl_steps(current)

    assert fields["protocol"] == "UDP"
    assert fields["dst_port"] == "80"
    assert mock_q.select.call_args.kwargs.get("default") == "TCP"
    text_defaults = [c.kwargs.get("default") for c in mock_q.text.call_args_list]
    assert text_defaults == ["0.0.0.0", "0", "Any", "10.0.0.1", "32", "22"]


def test_acl_field_steps_icmp_skips_port_prompts():
    """ICMP はポート入力をスキップする"""
    from mdx_cli.commands.acl import _NEW_ACL_FIELDS

    with patch("mdx_cli.commands.acl.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "ICMP"
        mock_q.text.return_value.unsafe_ask.side_effect = [
            "0.0.0.0", "0",  # src（ポートなし）
            "10.0.0.1", "32",  # dst（ポートなし）
        ]
        _run_acl_steps(dict(_NEW_ACL_FIELDS))

    assert mock_q.text.return_value.unsafe_ask.call_count == 4


def test_acl_add_icmp_sends_any_ports_even_after_port_was_entered():
    """TCP でポートを入れてから ICMP に直しても、送るポートは Any にする"""
    with patch("mdx_cli.commands.acl.create_acl") as mock_create:
        with patch("mdx_cli.commands.acl.get_client"):
            with patch("mdx_cli.commands.acl.questionary") as mock_q:
                with patch("mdx_cli.commands._prompt_steps.questionary") as mock_steps_q:
                    # 1周目は TCP・ポート22、「直す」でプロトコルを ICMP にして最後まで聞き直す
                    mock_q.select.return_value.unsafe_ask.side_effect = ["TCP", "ICMP"]
                    mock_q.text.return_value.unsafe_ask.side_effect = [
                        "0.0.0.0", "0", "Any", "10.0.0.1", "32", "22",
                        "0.0.0.0", "0", "10.0.0.1", "32",
                    ]
                    mock_steps_q.select.return_value.unsafe_ask.side_effect = ["edit", 0, "execute"]
                    result = runner.invoke(app, ["add", "seg-1"])

    assert result.exit_code == 0, result.output
    request = mock_create.call_args.args[1]
    assert (request.protocol, request.src_port, request.dst_port) == ("ICMP", "Any", "Any")


def test_validate_prefix_length_accepts_only_0_to_32():
    """マスクはプレフィックス長（0〜32 の整数）だけを受け付け、ドット表記は理由を返す"""
    from mdx_cli.commands.acl import _validate_prefix_length

    assert _validate_prefix_length("0") is True
    assert _validate_prefix_length("32") is True
    assert isinstance(_validate_prefix_length("33"), str)
    assert isinstance(_validate_prefix_length("255.255.255.255"), str)
    assert isinstance(_validate_prefix_length(""), str)


def test_prompt_acl_fields_validates_mask_prompts():
    """マスクの入力欄にだけプレフィックス長の検証を付ける"""
    from mdx_cli.commands.acl import _NEW_ACL_FIELDS, _validate_prefix_length

    with patch("mdx_cli.commands.acl.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "TCP"
        mock_q.text.return_value.unsafe_ask.side_effect = [
            "0.0.0.0", "0", "Any", "10.0.0.1", "32", "22",
        ]
        _run_acl_steps(dict(_NEW_ACL_FIELDS))

    validators = [c.kwargs.get("validate") for c in mock_q.text.call_args_list]
    assert validators == [
        None, _validate_prefix_length, None, None, _validate_prefix_length, None,
    ]


def test_acl_list_json():
    acls = [_make_acl()]
    with patch("mdx_cli.commands.acl.list_acls", return_value=acls):
        with patch("mdx_cli.commands.acl.get_client"):
            result = runner.invoke(app, ["list", "seg-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["protocol"] == "TCP"


def test_acl_add_sends_request_and_reports_acceptance():
    """入力どおりの作成リクエストを送り、応答を読まずに受付を表示する"""
    with patch("mdx_cli.commands.acl.create_acl") as mock_create:
        with patch("mdx_cli.commands.acl.get_client"):
            with patch("mdx_cli.commands.acl.questionary") as mock_q:
                mock_q.select.return_value.unsafe_ask.return_value = "TCP"
                mock_q.text.return_value.unsafe_ask.side_effect = [
                    "0.0.0.0", "0", "Any",  # src
                    "10.0.0.1", "32", "22",  # dst
                ]
                with patch("mdx_cli.commands._prompt_steps.questionary") as mock_steps_q:
                    mock_steps_q.select.return_value.unsafe_ask.return_value = "execute"
                    result = runner.invoke(app, ["add", "seg-1"])

    assert result.exit_code == 0, result.output
    request = mock_create.call_args.args[1]
    assert request.model_dump() == {
        "protocol": "TCP",
        "src_address": "0.0.0.0",
        "src_mask": "0",
        "src_port": "Any",
        "dst_address": "10.0.0.1",
        "dst_mask": "32",
        "dst_port": "22",
        "segment": "seg-1",
    }
    assert "ACL作成リクエストを受け付けました" in result.output


def test_acl_edit_sends_request_and_reports_acceptance():
    """選んだACLへ更新リクエストを送り、応答を読まずに受付を表示する"""
    acl = _make_acl()
    with patch("mdx_cli.commands.acl.list_acls", return_value=[acl]):
        with patch("mdx_cli.commands.acl.update_acl") as mock_update:
            with patch("mdx_cli.commands.acl.get_client"):
                with patch("mdx_cli.commands.acl.resolve_segment_id", return_value="seg-1"):
                    with patch("mdx_cli.commands._common.questionary") as mock_common_q:
                        # ACL一覧からの番号選択（select_from_list 経由）
                        mock_common_q.text.return_value.unsafe_ask.return_value = "1"
                        with patch("mdx_cli.commands.acl.questionary") as mock_q:
                            mock_q.text.return_value.unsafe_ask.side_effect = [
                                "0.0.0.0", "0", "Any",  # src
                                "10.0.0.1", "32", "80",  # dst
                            ]
                            mock_q.select.return_value.unsafe_ask.return_value = "UDP"
                            with patch("mdx_cli.commands._prompt_steps.questionary") as mock_steps_q:
                                mock_steps_q.select.return_value.unsafe_ask.return_value = "execute"
                                result = runner.invoke(app, ["edit"])

    assert result.exit_code == 0, result.output
    acl_id, request = mock_update.call_args.args[1:]
    assert acl_id == "acl-1"
    assert request.protocol == "UDP"
    assert request.dst_port == "80"
    assert "ACL更新リクエストを受け付けました" in result.output


def test_acl_delete():
    with patch("mdx_cli.commands.acl.delete_acl") as mock_delete:
        with patch("mdx_cli.commands.acl.get_client"):
            result = runner.invoke(app, ["delete", "acl-1", "--yes"])
            assert result.exit_code == 0
            mock_delete.assert_called_once()
            assert "削除しました" in result.output
