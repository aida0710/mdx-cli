import json

from mdx_cli.models.vm import VM
from mdx_cli.output.formatting import render_json, render_table
from mdx_cli.output.tables import VM_COLUMNS


def _make_vm() -> VM:
    return VM(
        uuid="abc-123",
        name="test-vm",
        status="Running",
        project="proj-456",
        pack_type="cpu",
        pack_num=3,
        service_level="spot",
    )


def test_render_json_single(capsys):
    vm = _make_vm()
    render_json(vm)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["uuid"] == "abc-123"
    assert data["name"] == "test-vm"


def test_render_json_list(capsys):
    vms = [_make_vm(), _make_vm()]
    render_json(vms)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 2


def test_render_table(capsys):
    vm = _make_vm()
    render_table([vm], VM_COLUMNS)
    captured = capsys.readouterr()
    assert "abc-123" in captured.out
    assert "test-vm" in captured.out
