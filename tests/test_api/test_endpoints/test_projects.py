import httpx
import respx

from mdx_cli.api.endpoints.projects import list_projects, get_project_summary


@respx.mock
def test_list_projects():
    respx.get("/api/project/assigned/").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"uuid": "proj-1", "name": "Project 1", "description": "desc1"},
                    {"uuid": "proj-2", "name": "Project 2", "description": "desc2"},
                ]
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    projects = list_projects(client)
    assert len(projects) == 2
    assert projects[0].uuid == "proj-1"
    assert projects[1].name == "Project 2"


@respx.mock
def test_get_project_summary():
    respx.get("/api/project/proj-1/summary/").mock(
        return_value=httpx.Response(
            200,
            json={"uuid": "proj-1", "name": "Project 1", "description": "Summary"},
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    summary = get_project_summary(client, "proj-1")
    assert summary.uuid == "proj-1"
