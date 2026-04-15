import httpx

from mdx_cli.api.pagination import fetch_all
from mdx_cli.models.vm import VM, VMDeployRequest, VMDeployResponse


def list_vms(client: httpx.Client, project_id: str) -> list[VM]:
    items = fetch_all(client, f"/api/vm/project/{project_id}/")
    return [VM.model_validate(item) for item in items]


def get_vm(client: httpx.Client, vm_id: str) -> VM:
    resp = client.get(f"/api/vm/{vm_id}/")
    resp.raise_for_status()
    data = resp.json()
    if "uuid" not in data:
        data["uuid"] = vm_id
    return VM.model_validate(data)


def deploy_vm(client: httpx.Client, request: VMDeployRequest) -> VMDeployResponse:
    resp = client.post("/api/vm/deploy/", json=request.model_dump())
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data.get("task_id"), str):
        data["task_id"] = [data["task_id"]]
    return VMDeployResponse.model_validate(data)


def power_on_vm(client: httpx.Client, vm_id: str, service_level: str = "spot") -> None:
    resp = client.post(
        f"/api/vm/{vm_id}/power_on/", json={"service_level": service_level}
    )
    resp.raise_for_status()


def power_off_vm(client: httpx.Client, vm_id: str) -> None:
    resp = client.post(f"/api/vm/{vm_id}/power_off/")
    resp.raise_for_status()


def destroy_vm(client: httpx.Client, vm_id: str) -> VMDeployResponse:
    resp = client.post(f"/api/vm/{vm_id}/destroy/")
    resp.raise_for_status()
    data = resp.json()
    # task_id が文字列の場合はリストに変換
    if isinstance(data.get("task_id"), str):
        data["task_id"] = [data["task_id"]]
    return VMDeployResponse.model_validate(data)


def get_vm_csv(client: httpx.Client, vm_id: str) -> dict:
    """VM のネットワーク情報を CSV 用に取得する。"""
    resp = client.get(f"/api/vm/{vm_id}/csv")
    resp.raise_for_status()
    return resp.json()


def shutdown_vm(client: httpx.Client, vm_id: str) -> None:
    resp = client.post(f"/api/vm/{vm_id}/shutdown/")
    resp.raise_for_status()


def reboot_vm(client: httpx.Client, vm_id: str) -> None:
    resp = client.post(f"/api/vm/{vm_id}/reboot/")
    resp.raise_for_status()


def reset_vm(client: httpx.Client, vm_id: str) -> None:
    resp = client.post(f"/api/vm/{vm_id}/reset/")
    resp.raise_for_status()


def sync_vms(client: httpx.Client, project_id: str) -> None:
    resp = client.post(f"/api/vm/synchronize/project/{project_id}/")
    resp.raise_for_status()
