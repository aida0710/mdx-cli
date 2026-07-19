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
