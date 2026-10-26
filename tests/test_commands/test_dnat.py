import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mdx_cli.commands.dnat import app
from mdx_cli.models.network import DNAT, DNATRequest, Segment

runner = CliRunner()

_DNAT_FIELDS = {
    "uuid": "dnat-1",
    "pool_address": "203.0.113.10",
    "segment": "テストセグメント",
    "dst_address": "10.0.0.20",
}


def _make_dnat(**overrides):
    return DNAT(**{**_DNAT_FIELDS, **overrides})


def test_dnat_list_json():
    dnats = [_make_dnat()]
    with patch("mdx_cli.commands.dnat.list_dnats", return_value=dnats):
        with patch("mdx_cli.commands.dnat.get_client"):
            with patch("mdx_cli.commands.dnat.resolve_project_id", return_value="proj-1"):
                result = runner.invoke(app, ["list", "--json"])
                assert result.exit_code == 0
                data = json.loads(result.output)
                assert len(data) == 1
                assert data[0]["pool_address"] == "203.0.113.10"


def test_dnat_add_edit_reasks_from_chosen_step():
    """確認で「直す」→宛先アドレスを選ぶと、宛先だけ聞き直して送る"""
    segments = [Segment(uuid="seg-1", name="セグメント1")]
    with patch("mdx_cli.commands.dnat.create_dnat") as mock_create:
        with patch("mdx_cli.commands.dnat.get_client"):
            with patch("mdx_cli.commands.dnat.resolve_project_id", return_value="proj-1"):
                with patch("mdx_cli.commands.dnat.list_assignable_ips", return_value=["203.0.113.11", "203.0.113.12"]):
                    with patch("mdx_cli.commands.dnat.list_segments", return_value=segments):
                        with patch("mdx_cli.commands._common.questionary") as mock_common_q:
                            # IP一覧からの番号選択（select_from_list 経由）
                            mock_common_q.text.return_value.unsafe_ask.return_value = "2"
                            with patch("mdx_cli.commands.dnat.questionary") as mock_q:
                                mock_q.text.return_value.unsafe_ask.side_effect = ["10.0.0.1", "10.0.0.2"]
                                with patch("mdx_cli.commands._prompt_steps.questionary") as mock_steps_q:
                                    mock_steps_q.select.return_value.unsafe_ask.side_effect = [
                                        "edit", 2, "execute",
                                    ]
                                    result = runner.invoke(app, ["add"])

    assert result.exit_code == 0, result.output
    assert mock_q.text.call_args.kwargs["default"] == "10.0.0.1"
    request = mock_create.call_args.args[1]
    assert (request.pool_address, request.segment, request.dst_address) == (
        "203.0.113.12", "seg-1", "10.0.0.2",
    )


def test_dnat_edit_uses_current_values_as_defaults():
    """編集では今のグローバルIP・セグメント・宛先を初期値にする"""
    dnat = _make_dnat()
    segments = [Segment(uuid="seg-0", name="別のセグメント"), Segment(uuid="seg-1", name="テストセグメント")]
    with patch("mdx_cli.commands.dnat.update_dnat") as mock_update:
        with patch("mdx_cli.commands.dnat.get_client"):
            with patch("mdx_cli.commands.dnat.resolve_project_id", return_value="proj-1"):
                with patch("mdx_cli.commands.dnat.list_dnats", return_value=[dnat]):
                    with patch("mdx_cli.commands.dnat.list_assignable_ips", return_value=["203.0.113.11"]):
                        with patch("mdx_cli.commands.dnat.list_segments", return_value=segments):
                            with patch("mdx_cli.commands._common.questionary") as mock_common_q:
                                mock_common_q.text.side_effect = lambda label, default: _answer(default)
                                with patch("mdx_cli.commands.dnat.questionary") as mock_q:
                                    mock_q.text.side_effect = lambda label, default: _answer(default)
                                    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_steps_q:
                                        mock_steps_q.select.return_value.unsafe_ask.return_value = "execute"
                                        result = runner.invoke(app, ["edit", "dnat-1"])

    assert result.exit_code == 0, result.output
    assert mock_update.call_args.args[1:] == (
        "dnat-1",
        DNATRequest(pool_address="203.0.113.10", segment="seg-1", dst_address="10.0.0.20"),
    )


def _answer(value):
    """Enter で初期値のまま答える質問"""
    question = MagicMock()
    question.unsafe_ask.return_value = value
    return question


def test_dnat_delete():
    with patch("mdx_cli.commands.dnat.delete_dnat") as mock_delete:
        with patch("mdx_cli.commands.dnat.get_client"):
            with patch("mdx_cli.commands.dnat.resolve_project_id", return_value="proj-1"):
                result = runner.invoke(app, ["delete", "dnat-1", "--yes"])
                assert result.exit_code == 0
                mock_delete.assert_called_once()
                assert "受け付けました" in result.output
