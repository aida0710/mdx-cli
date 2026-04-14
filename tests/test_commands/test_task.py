import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.task import app
from mdx_cli.models.task import Task
from mdx_cli.models.history import HistoryEntry

runner = CliRunner()


def _make_task():
    return Task(
        uuid="task-1",
        type="デプロイ",
        object_uuid="vm-1",
        object_name="test-vm",
        start_datetime="2026-04-14 16:34:13",
        end_datetime=None,
        status="Running",
        progress=50,
    )


def _make_completed_task():
    return Task(
        uuid="task-1",
        type="デプロイ",
        object_uuid="vm-1",
        object_name="vm-1",
        start_datetime="2026-01-01",
        end_datetime="2026-01-01",
        status="Completed",
        progress=100,
    )


def _make_history_entry():
    return HistoryEntry(
        type="デプロイ",
        object_name="vm-1",
        status="Completed",
        start_datetime="2026-01-01",
        end_datetime="2026-01-01",
        user_name="user",
    )


def test_task_status_json():
    with patch("mdx_cli.commands.task.get_task", return_value=_make_task()):
        with patch("mdx_cli.commands.task.get_client"):
            result = runner.invoke(app, ["status", "task-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["uuid"] == "task-1"
            assert data["progress"] == 50


def test_task_list():
    entries = [_make_history_entry()]
    with patch("mdx_cli.commands.task.list_history", return_value=entries):
        with patch("mdx_cli.commands.task.get_client"):
            with patch("mdx_cli.commands.task.resolve_project_id", return_value="proj-1"):
                result = runner.invoke(app, ["list", "--project-id", "proj-1"])
                assert result.exit_code == 0
                assert "vm-1" in result.output


def test_task_wait():
    completed = _make_completed_task()
    with patch("mdx_cli.commands.task.wait_for_task", return_value=completed):
        with patch("mdx_cli.commands.task.get_client"):
            result = runner.invoke(app, ["wait", "task-1", "--json"])
            assert result.exit_code == 0
            # The output contains a status line before the JSON block
            json_start = result.output.index("{")
            data = json.loads(result.output[json_start:])
            assert data["uuid"] == "task-1"
            assert data["status"] == "Completed"
