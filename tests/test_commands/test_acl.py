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


def test_acl_list_json():
    acls = [_make_acl()]
    with patch("mdx_cli.commands.acl.list_acls", return_value=acls):
        with patch("mdx_cli.commands.acl.get_client"):
            result = runner.invoke(app, ["list", "seg-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["protocol"] == "TCP"


def test_acl_add_interactive():
    acl = _make_acl(uuid="acl-new")
    with patch("mdx_cli.commands.acl.create_acl", return_value=acl) as mock_create:
        with patch("mdx_cli.commands.acl.get_client"):
            with patch("mdx_cli.commands.acl.questionary") as mock_q:
                mock_q.select.return_value.unsafe_ask.return_value = "TCP"
                mock_q.text.return_value.unsafe_ask.side_effect = [
                    "0.0.0.0", "0.0.0.0", "Any",  # src
                    "10.0.0.1", "255.255.255.255", "22",  # dst
                ]
                mock_q.confirm.return_value.unsafe_ask.return_value = True
                result = runner.invoke(app, ["add", "seg-1", "--json"])
                assert result.exit_code == 0
                mock_create.assert_called_once()


def test_acl_edit_interactive():
    acl = _make_acl()
    acl_updated = _make_acl(protocol="UDP", dst_port="80")
    with patch("mdx_cli.commands.acl.list_acls", return_value=[acl]):
        with patch("mdx_cli.commands.acl.update_acl", return_value=acl_updated):
            with patch("mdx_cli.commands.acl.get_client"):
                with patch("mdx_cli.commands.acl.resolve_segment_id", return_value="seg-1"):
                    with patch("mdx_cli.commands.acl.questionary") as mock_q:
                        mock_q.text.return_value.unsafe_ask.side_effect = [
                            "1",  # 番号選択
                            "0.0.0.0", "0.0.0.0", "Any",  # src
                            "10.0.0.1", "32", "80",  # dst
                        ]
                        mock_q.select.return_value.unsafe_ask.return_value = "UDP"
                        mock_q.confirm.return_value.unsafe_ask.return_value = True
                        result = runner.invoke(app, ["edit", "--json"])
                        assert result.exit_code == 0


def test_acl_delete():
    with patch("mdx_cli.commands.acl.delete_acl") as mock_delete:
        with patch("mdx_cli.commands.acl.get_client"):
            result = runner.invoke(app, ["delete", "acl-1", "--yes"])
            assert result.exit_code == 0
            mock_delete.assert_called_once()
            assert "削除しました" in result.output
