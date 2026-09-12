"""画面実装の契約から作成した合成レスポンス。実APIの採取結果ではない。"""

import json

import httpx
import pytest
import respx

from mdx_cli.api.client import create_client
from mdx_cli.api.endpoints import projects


@pytest.fixture
def client():
    with create_client(token="test-jwt", silent=True) as client:
        yield client


@respx.mock
def test_assigned_tenant_without_uuid(client):
    route = respx.get("/api/project/assigned/").respond(200, json=[
        {"name": "Tenant", "projects": [
            {"uuid": "p1", "name": "Project", "type": 0, "expired": False, "suspended": True},
        ]},
        {"name": "Empty", "projects": []},
    ])
    tenants = projects.list_projects(client)
    assert tenants[0].projects[0].uuid == "p1"
    assert tenants[0].projects[0].model_dump()["suspended"] is True
    assert tenants[1].projects == []
    assert not route.calls[0].request.url.query


@respx.mock
def test_assigned_legacy_pagination_still_collects_all_projects(client):
    route = respx.get("/api/project/assigned/").mock(side_effect=[
        httpx.Response(200, json={"count": 2, "next": "?page=2", "results": [{"uuid": "p1", "name": "One"}]}),
        httpx.Response(200, json={"count": 2, "next": None, "results": [{"uuid": "p2", "name": "Two"}]}),
    ])
    assert [p.uuid for p in projects.list_projects(client)] == ["p1", "p2"]
    assert not route.calls[0].request.url.query
    assert dict(route.calls[1].request.url.params) == {"page": "2"}


@respx.mock
def test_resources_and_common_headers(client):
    payload = {"cpu_pack_max": 100, "cpu_pack": 12, "cpu_pack_max_current": 40,
               "cpu_pack_future": 30, "cpu_pack_rmin": 5, "global_ip": 3, "future_field": {"x": 1}}
    route = respx.get("/api/project/p1/resources/").respond(200, json=payload)
    assert projects.get_project_resources(client, "p1").model_dump() == payload
    request = route.calls[0].request
    assert request.headers["Authorization"] == "JWT test-jwt"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Accept-Language"] == "ja"


@respx.mock
def test_users_explicit_page_preserves_count_and_filters(client):
    route = respx.get("/api/user/project/p1/").respond(200, json={
        "count": 42, "next": None, "results": [
            {"uuid": "u1", "username": "A&B", "email": "a+b@example.test", "auth": 0},
        ],
    })
    users = projects.list_project_users(client, "p1", page=2, page_size=10,
                                        ordering="-username", username="A&B",
                                        email="a+b@example.test", auth="0")
    assert users.count == 42
    assert users.results[0].model_dump()["auth"] == 0
    assert dict(route.calls[0].request.url.params) == {
        "page": "2", "page_size": "10", "ordering": "-username", "username": "A&B",
        "email": "a+b@example.test", "auth": "0",
    }


@respx.mock
def test_users_default_collects_all_pages_and_keeps_filters(client):
    route = respx.get("/api/user/project/p1/").mock(side_effect=[
        httpx.Response(200, json={"count": 2, "next": "?page=2", "results": [
            {"uuid": "u1", "username": "one"},
        ]}),
        httpx.Response(200, json={"count": 2, "next": None, "results": [
            {"uuid": "u2", "username": "two"},
        ]}),
    ])
    users = projects.list_project_users(client, "p1", page_size=10, auth="admin")
    assert users.count == 2
    assert [u.uuid for u in users.results] == ["u1", "u2"]
    assert route.calls[1].request.url.params["page"] == "2"
    assert all(call.request.url.params["auth"] == "admin" for call in route.calls)


@respx.mock
def test_points_have_no_pagination_and_preserve_precision(client):
    payload = {"lastConsumed": "2026-09-12 00:00:00", "results": [
        {"point_id": 123, "purchase_points": "1000.0001", "used_points": "0.0001",
         "remaining_points": "1000.0000", "expiration_date": "2027-03-31"},
    ]}
    route = respx.get("/api/project/p1/point/").respond(200, json=payload)
    assert projects.get_project_points(client, "p1").model_dump() == payload
    assert not route.calls[0].request.url.query


@respx.mock
@pytest.mark.parametrize("input_type,start,end,lang", [
    (1, "", "", "jp"), (2, "", "", "jp"), (3, "", "", "jp"), (4, "", "", "jp"),
    (0, "2026-09-05 00", "2026-09-12 23", "en"),
])
def test_usage_posts_period(client, input_type, start, end, lang):
    route = respx.post("/api/project/p1/resource_usage/").respond(
        200, json={"html": "<table><tr><td>1,234.50</td></tr></table>", "err_msg": ""},
    )
    report = projects.get_project_resource_usage(
        client, "p1", input_type=input_type, start=start, end=end, lang=lang,
    )
    assert "1,234.50" in report.html
    assert json.loads(route.calls[0].request.content) == {
        "input_type": input_type, "start": start, "end": end, "lang": lang,
    }


@respx.mock
@pytest.mark.parametrize("section", ["resource", "resource_list", "vm", "spot_vm", "guarantee_vm"])
def test_overview_sections(client, section):
    payload = [{"name": "cpu"}] if section == "resource_list" else {"total": 3}
    respx.get(f"/api/project/p1/overview/{section}/").respond(200, json=payload)
    assert projects.get_project_overview_section(client, "p1", section) == payload


@respx.mock
def test_usage_http_failure_is_not_an_empty_report(client):
    respx.post("/api/project/p1/resource_usage/").respond(403)
    with pytest.raises(httpx.HTTPStatusError):
        projects.get_project_resource_usage(client, "p1")
