from unittest.mock import patch

import httpx
import respx

from mdx_cli.api.endpoints.auth import _parse_form, refresh_token, sso_login


def test_parse_form_extracts_fields():
    html = """
    <html><body>
    <form action="/idp/login?execution=e1s2" method="POST">
        <input type="hidden" name="csrf_token" value="abc123"/>
        <input type="text" name="j_username" value=""/>
        <input type="password" name="j_password" value=""/>
        <input type="submit" name="_eventId_proceed" value="Login"/>
    </form>
    </body></html>
    """
    action, fields = _parse_form(html)
    assert action == "/idp/login?execution=e1s2"
    assert fields["csrf_token"] == "abc123"
    assert "j_username" in fields
    assert "j_password" in fields


def test_parse_form_no_form_raises():
    import pytest
    with pytest.raises(ValueError, match="フォームが見つかりません"):
        _parse_form("<html><body>No form here</body></html>")


@respx.mock
def test_refresh_token_success():
    respx.post("/api/refresh/").mock(
        return_value=httpx.Response(200, json={"token": "jwt-refreshed"})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    new_token = refresh_token(client, "old-jwt")
    assert new_token == "jwt-refreshed"


@respx.mock
def test_refresh_token_failure():
    respx.post("/api/refresh/").mock(
        return_value=httpx.Response(401, json={"detail": "Token expired"})
    )
    client = httpx.Client(base_url="https://oprpl.mdx.jp")
    new_token = refresh_token(client, "expired-jwt")
    assert new_token is None


def test_sso_login_uses_ipv4_transport():
    """sso_login のセッションが IPv4 専用トランスポートを使用していること。"""
    with patch("mdx_cli.api.endpoints.auth.httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.get.side_effect = httpx.ConnectError("test")
        sso_login("https://oprpl.mdx.jp", "user", "pass", "123456")
        call_kwargs = mock_client_cls.call_args.kwargs
        transport = call_kwargs["transport"]
        assert isinstance(transport, httpx.HTTPTransport)
        assert transport._pool._local_address == "0.0.0.0"
