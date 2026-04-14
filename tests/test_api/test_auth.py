import httpx
import respx

from mdx_cli.api.auth import MDXAuth


def test_auth_injects_jwt_header():
    """保存済みトークンがあればAuthorizationヘッダーに注入される"""
    auth = MDXAuth(token="test-jwt-token")
    request = httpx.Request("GET", "https://oprpl.mdx.jp/api/project/assigned/")
    flow = auth.auth_flow(request)
    modified_request = next(flow)
    assert modified_request.headers["Authorization"] == "JWT test-jwt-token"


def test_auth_no_token():
    """トークンがなければヘッダーは付与されない"""
    auth = MDXAuth(token=None)
    request = httpx.Request("GET", "https://oprpl.mdx.jp/api/project/assigned/")
    flow = auth.auth_flow(request)
    modified_request = next(flow)
    assert "Authorization" not in modified_request.headers


@respx.mock
def test_auth_refreshes_on_401():
    """401応答時に自動でリフレッシュを試行する"""
    respx.get("https://oprpl.mdx.jp/api/project/assigned/").side_effect = [
        httpx.Response(401),
        httpx.Response(200, json={"results": []}),
    ]
    respx.post("https://oprpl.mdx.jp/api/refresh/").mock(
        return_value=httpx.Response(200, json={"token": "new-jwt"})
    )
    auth = MDXAuth(token="old-jwt")
    client = httpx.Client(base_url="https://oprpl.mdx.jp/", auth=auth)
    resp = client.get("/api/project/assigned/")
    assert resp.status_code == 200
    assert auth.token == "new-jwt"
