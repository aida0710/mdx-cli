from unittest.mock import patch

import httpx

from mdx_cli.api.endpoints.auth import _parse_form, sso_login


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


def test_sso_login_uses_ipv4_transport():
    """sso_login のセッションが IPv4 専用トランスポートを使用していること。"""
    with patch("mdx_cli.api.endpoints.auth.httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.get.side_effect = httpx.ConnectError("test")
        sso_login("https://oprpl.mdx.jp", "user", "pass", "123456")
        call_kwargs = mock_client_cls.call_args.kwargs
        transport = call_kwargs["transport"]
        assert isinstance(transport, httpx.HTTPTransport)
        assert transport._pool._local_address == "0.0.0.0"


def test_sso_login_calls_otp_provider_when_totp_form_is_submitted(mocker):
    """TOTPはSSO開始前ではなく、TOTPフォームへの送信直前に生成する。"""
    totp_form = httpx.Response(
        200,
        request=httpx.Request("GET", "https://idp.example.test/totp"),
        text='''<form action="/verify"><input name="j_tokenNumber" value=""></form>''',
    )
    token_page = httpx.Response(
        200,
        request=httpx.Request("POST", "https://idp.example.test/verify"),
        text="<script>localStorage.setItem('token', 'x'); token = 'aaa.bbb.ccc';</script>",
    )
    session = mocker.MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = totp_form
    provider = mocker.Mock(return_value="654321")

    def post(_url, *, data=None):
        provider.assert_called_once_with()
        assert data["j_tokenNumber"] == "654321"
        return token_page

    session.post.side_effect = post
    mocker.patch("mdx_cli.api.endpoints.auth.httpx.Client", return_value=session)

    token = sso_login("https://oprpl.mdx.jp", "user", "pass", provider)

    assert token == "aaa.bbb.ccc"
