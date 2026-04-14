import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.network import app
from mdx_cli.models.network import Segment, SegmentSummary

runner = CliRunner()


def test_segment_list_json():
    segments = [Segment(uuid="seg-1", name="Segment 1")]
    with patch("mdx_cli.commands.network.list_segments", return_value=segments):
        with patch("mdx_cli.commands.network.get_client"):
            result = runner.invoke(app, ["segment", "list", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1


def test_ips_json():
    ips = ["203.0.113.10", "203.0.113.11"]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=ips):
        with patch("mdx_cli.commands.network.get_client"):
            result = runner.invoke(app, ["ips", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data == ["203.0.113.10", "203.0.113.11"]


def test_ips_table():
    ips = ["203.0.113.10", "203.0.113.11"]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=ips):
        with patch("mdx_cli.commands.network.get_client"):
            result = runner.invoke(app, ["ips", "--project-id", "proj-1"])
            assert result.exit_code == 0
            assert "203.0.113.10" in result.output
            assert "203.0.113.11" in result.output


def test_segment_show():
    summary = SegmentSummary(vlan_id=100, vni=10000, ip_range="192.168.1.0/24")
    with patch("mdx_cli.commands.network.resolve_segment_id", return_value="seg-1"):
        with patch("mdx_cli.commands.network.get_segment_summary", return_value=summary):
            with patch("mdx_cli.commands.network.get_client"):
                result = runner.invoke(app, ["segment", "show", "seg-1", "--project-id", "proj-1"])
                assert result.exit_code == 0
                assert "192.168.1.0/24" in result.output
