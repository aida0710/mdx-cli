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
