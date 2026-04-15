import json
from unittest.mock import patch, call

from typer.testing import CliRunner

from mdx_cli.commands.vm import app
from mdx_cli.models.vm import VM

runner = CliRunner()


def _make_vm(name="test-vm", uuid="00000000-0000-0000-0000-000000000001", status="PowerON"):
    return VM(
        uuid=uuid,
        name=name,
        status=status,
        service_level="スポット仮想マシン",
    )


def test_vm_list_json():
    with patch("mdx_cli.commands.vm.list_vms", return_value=[_make_vm()]):
        with patch("mdx_cli.commands.vm.get_client"):
            result = runner.invoke(app, ["list", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1


def test_vm_show_json():
    vm = _make_vm()
    with patch("mdx_cli.commands.vm.get_vm", return_value=vm):
        with patch("mdx_cli.commands.vm.get_client"):
            result = runner.invoke(app, ["show", vm.uuid, "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["name"] == "test-vm"


def test_vm_stop_by_uuid():
    """UUID指定で1台停止"""
    vm = _make_vm()
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=[vm]):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}]) as mock_action:
            with patch("mdx_cli.commands.vm.get_client"):
                result = runner.invoke(app, ["stop", vm.uuid])
                assert result.exit_code == 0
                mock_action.assert_called_once()


def test_vm_stop_by_pattern():
    """パターン指定で複数台停止"""
    vms = [_make_vm("crawler-a-0", "uuid-1"), _make_vm("crawler-a-1", "uuid-2")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}, {}]) as mock_action:
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.questionary") as mock_q:
                    mock_q.confirm.return_value.unsafe_ask.return_value = True
                    result = runner.invoke(app, ["stop", "crawler-*", "-p", "proj-1"])
                    assert result.exit_code == 0
                    mock_action.assert_called_once()


def test_vm_start_pattern():
    """パターン指定で複数台起動"""
    vms = [_make_vm("web-0", "uuid-3"), _make_vm("web-1", "uuid-4")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}, {}]) as mock_action:
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.questionary") as mock_q:
                    mock_q.confirm.return_value.unsafe_ask.return_value = True
                    result = runner.invoke(app, ["start", "web-*", "-p", "proj-1"])
                    assert result.exit_code == 0
                    mock_action.assert_called_once()


def test_vm_destroy_single():
    """UUID指定で1台削除（停止済み）"""
    vm = _make_vm(status="PowerOFF")
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=[vm]):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{"task_id": "task-1"}]):
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.questionary") as mock_q:
                    mock_q.confirm.return_value.unsafe_ask.return_value = True
                    result = runner.invoke(app, ["destroy", vm.uuid, "--no-wait"])
                    assert result.exit_code == 0
