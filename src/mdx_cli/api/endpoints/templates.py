import httpx

from mdx_cli.api.pagination import fetch_all
from mdx_cli.models.template import Template


def list_templates(client: httpx.Client, project_id: str) -> list[Template]:
    items = fetch_all(client, f"/api/catalog/project/{project_id}/")
    return [Template.model_validate(item) for item in items]
