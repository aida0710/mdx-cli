import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.project import app
from mdx_cli.models.project import Project, StorageInfo

runner = CliRunner()


def test_project_list_json():
    mock_projects = [
        Project(uuid="proj-1", name="Project 1", description="desc1"),
        Project(uuid="proj-2", name="Project 2", description="desc2"),
    ]
    with patch("mdx_cli.commands.project.list_projects", return_value=mock_projects):
        with patch("mdx_cli.commands.project.get_client"):
            result = runner.invoke(app, ["list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 2
            assert data[0]["uuid"] == "proj-1"


def test_project_list_table():
    mock_projects = [
        Project(uuid="proj-1", name="Project 1", description="desc1"),
    ]
    with patch("mdx_cli.commands.project.list_projects", return_value=mock_projects):
        with patch("mdx_cli.commands.project.get_client"):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "proj-1" in result.output


def test_project_summary():
    overview = {
        "spot_vm": {"power_on": 2, "power_off": 1, "deallocated": 0, "total": 3},
        "guarantee_vm": {"power_on": 0, "power_off": 0, "deallocated": 0, "total": 0},
        "resource": {
            "disk_size": {"used": 100, "unused": 900},
            "cpu_pack": {"used": 0, "unused": 0},
            "gpu_pack": {"used": 0, "unused": 0},
        },
    }
    storage = StorageInfo()
    with patch("mdx_cli.commands.project.get_project_overview", return_value=overview):
        with patch("mdx_cli.commands.project.get_project_storage", return_value=storage):
            with patch("mdx_cli.commands.project.get_client"):
                with patch("mdx_cli.commands.project.resolve_project_id", return_value="proj-1"):
                    result = runner.invoke(app, ["summary", "--project-id", "proj-1"])
                    assert result.exit_code == 0
                    assert "2" in result.output  # power_on count
                    assert "3" in result.output  # total VM count


def test_project_select():
    org = Project(uuid="org-1", name="Org 1", description="")
    # Attach nested projects via model_extra
    org.model_extra["projects"] = [
        {"uuid": "proj-a", "name": "Project A"},
        {"uuid": "proj-b", "name": "Project B"},
    ]
    with patch("mdx_cli.commands.project.list_projects", return_value=[org]):
        with patch("mdx_cli.commands.project.get_client"):
            with patch("mdx_cli.commands.project.questionary") as mock_q:
                mock_q.text.return_value.unsafe_ask.return_value = "1"
                with patch("mdx_cli.credentials.store.CredentialStore.save_project_id") as mock_save:
                    result = runner.invoke(app, ["select"])
                    assert result.exit_code == 0
                    mock_save.assert_called_once_with("proj-a")
