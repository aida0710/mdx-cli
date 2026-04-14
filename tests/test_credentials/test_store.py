import json
from pathlib import Path

from mdx_cli.credentials.store import CredentialStore


def test_save_and_load_credentials(tmp_path, mocker):
    """keyringが使えない場合、Fernetフォールバックで保存・読込できる"""
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    store.save_credentials("testuser", "testpass")
    username, password = store.load_credentials()
    assert username == "testuser"
    assert password == "testpass"


def test_delete_credentials(tmp_path, mocker):
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    store.save_credentials("testuser", "testpass")
    store.delete_credentials()
    result = store.load_credentials()
    assert result is None


def test_save_and_load_token(tmp_path):
    store = CredentialStore(config_dir=tmp_path)
    store.save_token("jwt-token-abc")
    token = store.load_token()
    assert token == "jwt-token-abc"


def test_delete_token(tmp_path):
    store = CredentialStore(config_dir=tmp_path)
    store.save_token("jwt-token-abc")
    store.delete_token()
    token = store.load_token()
    assert token is None


def test_load_credentials_when_none_saved(tmp_path, mocker):
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    result = store.load_credentials()
    assert result is None
