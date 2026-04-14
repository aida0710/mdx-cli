import httpx
import respx

from mdx_cli.api.endpoints.templates import list_templates
from mdx_cli.models.template import Template


@respx.mock
def test_list_templates_returns_template_models():
    """list_templatesがTemplateモデルのリストを返す"""
    respx.get("/api/catalog/project/proj-1/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "uuid": "tmpl-1",
                    "name": "Ubuntu 22.04",
                    "template_name": "ubuntu-22.04",
                    "os_type": "Linux",
                    "os_name": "Ubuntu",
                    "os_version": "22.04",
                    "gpu_required": False,
                    "lower_limit_disk": 40,
                    "login_username": "mdxuser",
                    "description": "Ubuntu 22.04 LTS",
                },
                {
                    "uuid": "tmpl-2",
                    "name": "Windows Server 2022",
                    "template_name": "windows-2022",
                    "os_type": "Windows",
                    "os_name": "Windows Server",
                    "os_version": "2022",
                    "gpu_required": False,
                    "lower_limit_disk": 60,
                    "login_username": "Administrator",
                    "description": "Windows Server 2022",
                },
            ],
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    templates = list_templates(client, "proj-1")
    assert len(templates) == 2
    assert all(isinstance(t, Template) for t in templates)
    assert templates[0].uuid == "tmpl-1"
    assert templates[0].name == "Ubuntu 22.04"
    assert templates[1].uuid == "tmpl-2"
    assert templates[1].os_type == "Windows"


@respx.mock
def test_list_templates_paginated_response():
    """ページネーションレスポンス（results形式）を処理できる"""
    respx.get("/api/catalog/project/proj-2/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "uuid": "tmpl-3",
                        "name": "CentOS 7",
                        "template_name": "centos-7",
                        "os_type": "Linux",
                        "os_name": "CentOS",
                        "os_version": "7",
                        "gpu_required": False,
                        "lower_limit_disk": 40,
                        "login_username": "mdxuser",
                        "description": "CentOS 7",
                    }
                ],
            },
        )
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    templates = list_templates(client, "proj-2")
    assert len(templates) == 1
    assert isinstance(templates[0], Template)
    assert templates[0].uuid == "tmpl-3"
    assert templates[0].os_name == "CentOS"


@respx.mock
def test_list_templates_empty_response():
    """テンプレートが0件の場合は空リストを返す"""
    respx.get("/api/catalog/project/proj-3/").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    templates = list_templates(client, "proj-3")
    assert templates == []
