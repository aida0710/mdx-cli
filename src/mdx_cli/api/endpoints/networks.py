import httpx

from mdx_cli.api.pagination import fetch_all
from mdx_cli.models.network import (
    ACL,
    ACLCreateRequest,
    ACLUpdateRequest,
    DNAT,
    DNATRequest,
    Segment,
    SegmentSummary,
)


def list_segments(client: httpx.Client, project_id: str) -> list[Segment]:
    items = fetch_all(client, f"/api/segment/project/{project_id}/all/")
    return [Segment.model_validate(item) for item in items]


def get_segment_summary(client: httpx.Client, segment_id: str) -> SegmentSummary:
    resp = client.get(f"/api/segment/{segment_id}/summary/")
    resp.raise_for_status()
    return SegmentSummary.model_validate(resp.json())


def list_acls(client: httpx.Client, segment_id: str) -> list[ACL]:
    items = fetch_all(client, f"/api/acl/segment/{segment_id}/")
    return [ACL.model_validate(item) for item in items]


def list_dnats(client: httpx.Client, project_id: str) -> list[DNAT]:
    items = fetch_all(client, f"/api/dnat/project/{project_id}/")
    return [DNAT.model_validate(item) for item in items]


def create_acl(client: httpx.Client, request: ACLCreateRequest) -> ACL:
    resp = client.post("/api/acl/", json=request.model_dump())
    resp.raise_for_status()
    return ACL.model_validate(resp.json())


def update_acl(
    client: httpx.Client, acl_id: str, request: ACLUpdateRequest
) -> ACL:
    resp = client.put(f"/api/acl/{acl_id}/", json=request.model_dump())
    resp.raise_for_status()
    return ACL.model_validate(resp.json())


def delete_acl(client: httpx.Client, acl_id: str) -> None:
    resp = client.delete(f"/api/acl/{acl_id}/")
    resp.raise_for_status()


def create_dnat(client: httpx.Client, request: DNATRequest) -> None:
    resp = client.post("/api/dnat/", json=request.model_dump())
    resp.raise_for_status()


def update_dnat(
    client: httpx.Client, dnat_id: str, request: DNATRequest
) -> None:
    resp = client.put(f"/api/dnat/{dnat_id}/", json=request.model_dump())
    resp.raise_for_status()


def delete_dnat(client: httpx.Client, dnat_id: str) -> None:
    resp = client.delete(f"/api/dnat/{dnat_id}/")
    resp.raise_for_status()


def list_assignable_ips(client: httpx.Client, project_id: str) -> list[str]:
    resp = client.get(f"/api/global_ip/project/{project_id}/assignable/")
    resp.raise_for_status()
    return resp.json()
