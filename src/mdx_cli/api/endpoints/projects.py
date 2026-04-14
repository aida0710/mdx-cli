import httpx

from mdx_cli.api.pagination import fetch_all
from mdx_cli.models.project import AccessKey, Project, ProjectSummary, StorageInfo


def list_projects(client: httpx.Client) -> list[Project]:
    items = fetch_all(client, "/api/project/assigned/")
    return [Project.model_validate(item) for item in items]


def get_project_summary(client: httpx.Client, project_id: str) -> ProjectSummary:
    resp = client.get(f"/api/project/{project_id}/summary/")
    resp.raise_for_status()
    return ProjectSummary.model_validate(resp.json())


def get_project_storage(client: httpx.Client, project_id: str) -> StorageInfo:
    resp = client.get(f"/api/project/{project_id}/storage/")
    resp.raise_for_status()
    return StorageInfo.model_validate(resp.json())


def get_project_overview(client: httpx.Client, project_id: str) -> dict:
    """プロジェクト概要（VM数・リソース使用量）を取得する。"""
    spot = client.get(f"/api/project/{project_id}/overview/spot_vm/")
    spot.raise_for_status()
    guarantee = client.get(f"/api/project/{project_id}/overview/guarantee_vm/")
    guarantee.raise_for_status()
    resource = client.get(f"/api/project/{project_id}/overview/resource/")
    resource.raise_for_status()
    return {
        "spot_vm": spot.json(),
        "guarantee_vm": guarantee.json(),
        "resource": resource.json(),
    }


def list_access_keys(client: httpx.Client, project_id: str) -> list[AccessKey]:
    items = fetch_all(client, f"/api/project/{project_id}/access_key/")
    return [AccessKey.model_validate(item) for item in items]
