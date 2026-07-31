import httpx
import respx

from mdx_cli.api.endpoints.vms import (
    deploy_vm,
    destroy_vm,
    get_vm,
    list_vms,
    power_off_vm,
    power_on_vm,
    rename_vm,
)
from mdx_cli.models.vm import VMDeployRequest


@respx.mock
def test_list_vms():
    respx.get("/api/vm/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "uuid": "vm-1",
                    "name": "test-vm",
                    "status": "PowerON",
                    "service_level": "スポット仮想マシン",
                }
            ],
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    vms = list_vms(client, "proj-1")
    assert len(vms) == 1
    assert vms[0].uuid == "vm-1"


@respx.mock
def test_get_vm():
    respx.get("/api/vm/vm-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "vm-1",
                "name": "test-vm",
                "status": "PowerON",
                "service_level": "スポット仮想マシン",
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    vm = get_vm(client, "vm-1")
    assert vm.name == "test-vm"


@respx.mock
def test_deploy_vm():
    respx.post("/api/vm/deploy/").mock(
        return_value=httpx.Response(200, json={"task_id": ["task-abc"]})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    req = VMDeployRequest(
        catalog="cat-1",
        project="proj-1",
        vm_name="my-vm",
        network_adapters=[{"adapter_number": 1, "segment": "seg-1"}],
        shared_key="ssh-rsa AAAA...",
        template_name="ubuntu-22",
    )
    resp = deploy_vm(client, req)
    assert resp.task_id == ["task-abc"]


@respx.mock
def test_power_on_vm():
    respx.post("/api/vm/vm-1/power_on/").mock(
        return_value=httpx.Response(200, json={})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    power_on_vm(client, "vm-1", "spot")


@respx.mock
def test_power_off_vm():
    respx.post("/api/vm/vm-1/power_off/").mock(
        return_value=httpx.Response(200, json={})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    power_off_vm(client, "vm-1")


@respx.mock
def test_destroy_vm():
    respx.post("/api/vm/vm-1/destroy/").mock(
        return_value=httpx.Response(200, json={"task_id": ["task-del"]})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    resp = destroy_vm(client, "vm-1")
    assert resp.task_id == ["task-del"]

@respx.mock
def test_rename_vm_with_string_task_id():
    route = respx.post("/api/vm/vm-1/rename/").mock(
        return_value=httpx.Response(202, json={"task_id": "task-rename"})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")

    task_id = rename_vm(client, "vm-1", "renamed-vm")

    assert task_id == "task-rename"
    assert route.calls.last.request.content == b'{"vm_name":"renamed-vm"}'


@respx.mock
def test_rename_vm_with_list_task_id():
    respx.post("/api/vm/vm-1/rename/").mock(
        return_value=httpx.Response(202, json={"task_id": ["task-rename"]})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")

    task_id = rename_vm(client, "vm-1", "renamed-vm")

    assert task_id == "task-rename"


def test_vm_action_path():
    """VM操作APIのパスを一元的に構築する。"""
    from mdx_cli.api.endpoints.vms import vm_action_path

    assert vm_action_path("uuid-1", "power_on") == "/api/vm/uuid-1/power_on/"
    assert vm_action_path("uuid-2", "destroy") == "/api/vm/uuid-2/destroy/"
