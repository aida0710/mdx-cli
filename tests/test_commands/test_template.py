import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.template import app
from mdx_cli.models.network import Segment
from mdx_cli.models.template import Template

runner = CliRunner()


def test_template_list_json():
    templates = [Segment(uuid="tmpl-1", name="Ubuntu 22.04")]
    with patch("mdx_cli.commands.template.list_templates", return_value=templates):
        with patch("mdx_cli.commands.template.get_client"):
            result = runner.invoke(app, ["list", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1


def test_template_show_json():
    tmpl = Template(uuid="t1", name="Ubuntu 22.04")
    with patch("mdx_cli.commands.template.list_templates", return_value=[tmpl]):
        with patch("mdx_cli.commands.template.get_client"):
            with patch("mdx_cli.commands.template.resolve_project_id", return_value="proj-1"):
                result = runner.invoke(app, ["show", "t1", "--project-id", "proj-1", "--json"])
                assert result.exit_code == 0
                data = json.loads(result.output)
                assert data["uuid"] == "t1"
                assert data["name"] == "Ubuntu 22.04"
