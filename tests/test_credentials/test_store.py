
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

def test_load_token_returns_none_for_broken_json(tmp_path):
    """壊れた token.json はクラッシュせず未保存扱いにする（再ログインで自己修復）。"""
    store = CredentialStore(config_dir=tmp_path)
    (tmp_path / "token.json").write_text("{broken")
    assert store.load_token() is None


def test_load_project_id_returns_none_for_broken_json(tmp_path):
    """壊れた project.json も同様に未保存扱いにする。"""
    store = CredentialStore(config_dir=tmp_path)
    (tmp_path / "project.json").write_text("not json at all")
    assert store.load_project_id() is None


def test_keyring_available_is_cached(mocker):
    """keyring の疎通確認は初回のみ実行する（毎回叩くとバックエンドが遅い）。"""
    from mdx_cli.credentials import store as store_mod

    mock_keyring = mocker.MagicMock()
    mocker.patch.dict("sys.modules", {"keyring": mock_keyring})
    store_mod.keyring_available.cache_clear()

    assert store_mod.keyring_available() is True
    assert store_mod.keyring_available() is True
    assert mock_keyring.get_password.call_count == 1


def test_get_store_returns_same_instance(monkeypatch, tmp_path):
    """get_store() はキャッシュされた同一インスタンスを返す"""
    from mdx_cli.credentials.store import get_store

    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    get_store.cache_clear()
    assert get_store() is get_store()
    assert get_store()._config_dir == tmp_path


def test_save_and_load_totp_secret(tmp_path, mocker):
    """TOTPシークレットは所有ユーザーとセットで保存・読込される"""
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    store.save_totp_secret("testuser", "GEZDGNBVGY3TQOJQ")
    assert store.load_totp_secret() == ("testuser", "GEZDGNBVGY3TQOJQ")


def test_load_totp_secret_when_none_saved(tmp_path, mocker):
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    assert store.load_totp_secret() is None


def test_load_totp_secret_returns_none_for_corrupt_encrypted_file(tmp_path, mocker):
    """保存ファイルが途中書き込み等で壊れても、ログインは手入力へ戻れる。"""
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    (tmp_path / "totp.enc").write_bytes(b"not-a-fernet-token")

    assert store.load_totp_secret() is None


def test_load_totp_secret_returns_none_for_missing_fields(tmp_path, mocker):
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    store._write_fernet("totp.enc", {"username": "alice"})

    assert store.load_totp_secret() is None


def test_delete_credentials_also_deletes_totp_secret(tmp_path, mocker):
    """logout（delete_credentials）でTOTPシークレットも消える。

    ID/PWだけ消えてシークレットが残ると、別ユーザーのOTPを生成し続けてしまう。
    """
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    store.save_credentials("testuser", "testpass")
    store.save_totp_secret("testuser", "GEZDGNBVGY3TQOJQ")
    store.delete_credentials()
    assert store.load_totp_secret() is None


def test_delete_totp_secret(tmp_path, mocker):
    """ID/PWは残したままTOTPシークレットだけ解除できる。"""
    mocker.patch("mdx_cli.credentials.store.keyring_available", return_value=False)
    store = CredentialStore(config_dir=tmp_path)
    store.save_credentials("testuser", "testpass")
    store.save_totp_secret("testuser", "GEZDGNBVGY3TQOJQ")
    store.delete_totp_secret()
    assert store.load_totp_secret() is None
    assert store.load_credentials() == ("testuser", "testpass")
