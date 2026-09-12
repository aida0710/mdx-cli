import httpx

from mdx_cli.api.pagination import fetch_all
from mdx_cli.models.project import (
    AccessKey, AssignedTenant, OverviewKind, Project, ProjectPoints, ProjectResources,
    ProjectSummary, ProjectUsers, ResourceUsage, StorageInfo,
)


def list_projects(client: httpx.Client) -> list[AssignedTenant | Project]:
    """テナント配下の所属一覧を取得。従来のフラットな形式も受け付ける。"""
    items = fetch_all(client, "/api/project/assigned/", page_size=None)
    return [
        AssignedTenant.model_validate(item) if "projects" in item else Project.model_validate(item)
        for item in items
    ]


def get_project_resources(client: httpx.Client, project_id: str) -> ProjectResources:
    resp = client.get(f"/api/project/{project_id}/resources/")
    resp.raise_for_status()
    return ProjectResources.model_validate(resp.json())


def list_project_users(
    client: httpx.Client,
    project_id: str,
    *,
    page: int | None = None,
    page_size: int = 100,
    ordering: str | None = None,
    username: str | None = None,
    email: str | None = None,
    auth: str | None = None,
) -> ProjectUsers:
    """page未指定なら全ページ、指定時は総件数を含む1ページを返す。"""
    params = {key: value for key, value in {
        "page_size": page_size, "ordering": ordering, "username": username,
        "email": email, "auth": auth,
    }.items() if value is not None}
    path = f"/api/user/project/{project_id}/"
    if page is None:
        items = fetch_all(client, path, params={**params, "page": 1})
        return ProjectUsers.model_validate({"count": len(items), "results": items})
    resp = client.get(path, params={**params, "page": page})
    resp.raise_for_status()
    return ProjectUsers.model_validate(resp.json())


def get_project_points(client: httpx.Client, project_id: str) -> ProjectPoints:
    # ポイント一覧はサーバー側のページ分割なし。
    resp = client.get(f"/api/project/{project_id}/point/")
    resp.raise_for_status()
    return ProjectPoints.model_validate(resp.json())


def get_project_resource_usage(
    client: httpx.Client,
    project_id: str,
    *,
    input_type: int = 1,
    start: str = "",
    end: str = "",
    lang: str = "jp",
) -> ResourceUsage:
    """読み取り用POST。日時文字列のタイムゾーン変換は行わない。"""
    resp = client.post(f"/api/project/{project_id}/resource_usage/", json={
        "input_type": input_type, "start": start, "end": end, "lang": lang,
    })
    resp.raise_for_status()
    return ResourceUsage.model_validate(resp.json())


def get_project_overview_section(client: httpx.Client, project_id: str, section: str) -> dict | list:
    kind = OverviewKind(section)
    if kind == OverviewKind.all:
        raise ValueError("単一の概要種別を指定してください")
    resp = client.get(f"/api/project/{project_id}/overview/{kind.value}/")
    resp.raise_for_status()
    return resp.json()


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
