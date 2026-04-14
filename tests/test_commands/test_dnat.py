import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.dnat import app
from mdx_cli.models.network import DNAT

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


def test_dnat_add_interactive():
    with patch("mdx_cli.commands.dnat.create_dnat") as mock_create:
        with patch("mdx_cli.commands.dnat.get_client"):
            with patch("mdx_cli.commands.dnat.resolve_project_id", return_value="proj-1"):
                with patch("mdx_cli.commands.dnat.list_assignable_ips", return_value=["203.0.113.11"]):
                    with patch("mdx_cli.commands.dnat.resolve_segment_id", return_value="seg-1"):
                        with patch("mdx_cli.commands.dnat.questionary") as mock_q:
                            mock_q.text.return_value.unsafe_ask.side_effect = ["1", "10.0.0.1"]
                            mock_q.confirm.return_value.unsafe_ask.return_value = True
                            result = runner.invoke(app, ["add"])
                            assert result.exit_code == 0
                            mock_create.assert_called_once()


def test_dnat_delete():
    with patch("mdx_cli.commands.dnat.delete_dnat") as mock_delete:
        with patch("mdx_cli.commands.dnat.get_client"):
            with patch("mdx_cli.commands.dnat.resolve_project_id", return_value="proj-1"):
                result = runner.invoke(app, ["delete", "dnat-1", "--yes"])
                assert result.exit_code == 0
                mock_delete.assert_called_once()
                assert "受け付けました" in result.output
