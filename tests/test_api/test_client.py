import httpx

from mdx_cli.api.client import create_client


def test_create_client_default_base_url():
    client = create_client()
    assert str(client.base_url) == "https://oprpl.mdx.jp/"


def test_create_client_custom_base_url():
    client = create_client(base_url="https://test.example.com")
    assert str(client.base_url) == "https://test.example.com/"


def test_create_client_with_token():
    client = create_client(token="my-jwt")
    assert client.auth is not None


def test_create_client_uses_ipv4_transport():
    """httpx.Client が IPv4 専用トランスポートを使用していること。"""
    client = create_client()
    transport = client._transport
    assert isinstance(transport, httpx.HTTPTransport)
    assert transport._pool._local_address == "0.0.0.0"

def test_create_client_returns_mdx_client_with_spinner():
    """create_client は型付きの spinner 属性を持つ MDXClient を返す。"""
    from mdx_cli.api.client import MDXClient
    from mdx_cli.api.spinner import RequestSpinner

    client = create_client()
    assert isinstance(client, MDXClient)
    assert isinstance(client.spinner, RequestSpinner)


def test_relogin_uses_saved_totp_secret(mocker):
    """再ログインでもTOTPをSSOフォーム送信時まで生成しない。"""
    from mdx_cli.api.client import _make_relogin_fn
    from mdx_cli.credentials.totp import generate_totp
    from mdx_cli.settings import Settings

    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    store = mocker.MagicMock()
    store.load_credentials.return_value = ("saved_user", "saved_pass")
    store.load_totp_secret.return_value = ("saved_user", secret)
    mocker.patch("mdx_cli.credentials.store.get_store", return_value=store)
    generated_otp = None

    def fake_sso_login(**kwargs):
        nonlocal generated_otp
        assert callable(kwargs["otp"])
        generated_otp = kwargs["otp"]()
        return "new-token"

    mock_sso = mocker.patch("mdx_cli.api.endpoints.auth.sso_login", side_effect=fake_sso_login)

    token = _make_relogin_fn(Settings())()

    assert token == "new-token"
    assert generated_otp == generate_totp(secret)
    mock_sso.assert_called_once()
    store.save_token.assert_called_once_with("new-token")
