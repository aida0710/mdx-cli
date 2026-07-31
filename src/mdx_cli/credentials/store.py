import json
import os
import platform
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet


SERVICE_NAME = "mdx-cli"


@lru_cache
def keyring_available() -> bool:
    """keyringバックエンドが使えるか判定する。

    バックエンドによっては疎通確認自体が遅いため、プロセス内でキャッシュする。
    テストで差し替える場合は cache_clear() を呼ぶこと。
    """
    try:
        import keyring
        keyring.get_password(SERVICE_NAME, "__test__")
        return True
    except Exception:
        return False


def _derive_key(config_dir: Path) -> bytes:
    """ランダムソルト + PBKDF2 でキーを導出する（Fernetフォールバック用）"""
    import hashlib
    import base64

    salt_file = config_dir / ".salt"
    if salt_file.exists():
        salt = salt_file.read_bytes()
    else:
        salt = os.urandom(32)
        config_dir.mkdir(parents=True, exist_ok=True)
        salt_file.write_bytes(salt)
        os.chmod(salt_file, 0o600)

    machine_id = f"{platform.node()}-{platform.machine()}".encode()
    key = hashlib.pbkdf2_hmac("sha256", machine_id, salt, iterations=100_000)
    return base64.urlsafe_b64encode(key)


class CredentialStore:
    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = Path.home() / ".config" / "mdx-cli"
        self._config_dir = config_dir
        self._config_dir.mkdir(parents=True, exist_ok=True)

    def save_credentials(self, username: str, password: str) -> None:
        if keyring_available():
            import keyring
            keyring.set_password(SERVICE_NAME, "username", username)
            keyring.set_password(SERVICE_NAME, "password", password)
        else:
            self._save_credentials_fernet(username, password)

    def load_credentials(self) -> tuple[str, str] | None:
        if keyring_available():
            import keyring
            username = keyring.get_password(SERVICE_NAME, "username")
            password = keyring.get_password(SERVICE_NAME, "password")
            if username and password:
                return (username, password)
            return None
        else:
            return self._load_credentials_fernet()

    def delete_credentials(self) -> None:
        if keyring_available():
            import keyring
            try:
                keyring.delete_password(SERVICE_NAME, "username")
                keyring.delete_password(SERVICE_NAME, "password")
            except keyring.errors.PasswordDeleteError:
                pass
        else:
            cred_file = self._config_dir / "credentials.enc"
            if cred_file.exists():
                cred_file.unlink()

    def save_token(self, token: str) -> None:
        token_file = self._config_dir / "token.json"
        token_file.write_text(json.dumps({"token": token}))
        os.chmod(token_file, 0o600)

    def load_token(self) -> str | None:
        return self._read_json_field(self._config_dir / "token.json", "token")

    def delete_token(self) -> None:
        token_file = self._config_dir / "token.json"
        if token_file.exists():
            token_file.unlink()

    def save_project_id(self, project_id: str) -> None:
        project_file = self._config_dir / "project.json"
        project_file.write_text(json.dumps({"project_id": project_id}))
        os.chmod(project_file, 0o600)

    def load_project_id(self) -> str | None:
        return self._read_json_field(self._config_dir / "project.json", "project_id")

    @staticmethod
    def _read_json_field(path: Path, key: str) -> str | None:
        """JSONファイルから1フィールドを読む。

        未作成・破損・読み取り不可はいずれも None（未保存扱い）にする。
        壊れたファイルでコマンド全体をクラッシュさせず、再ログイン・再選択で
        自己修復できるようにするため。
        """
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        return data.get(key) if isinstance(data, dict) else None

    def _save_credentials_fernet(self, username: str, password: str) -> None:
        key = _derive_key(self._config_dir)
        f = Fernet(key)
        data = json.dumps({"username": username, "password": password}).encode()
        encrypted = f.encrypt(data)
        cred_file = self._config_dir / "credentials.enc"
        cred_file.write_bytes(encrypted)
        os.chmod(cred_file, 0o600)

    def _load_credentials_fernet(self) -> tuple[str, str] | None:
        cred_file = self._config_dir / "credentials.enc"
        if not cred_file.exists():
            return None
        key = _derive_key(self._config_dir)
        f = Fernet(key)
        decrypted = f.decrypt(cred_file.read_bytes())
        data = json.loads(decrypted)
        return (data["username"], data["password"])


@lru_cache
def get_store() -> CredentialStore:
    """共有のCredentialStoreインスタンスを返す。

    config_dir は get_settings() から解決する。
    テストで環境変数を変える場合は cache_clear() を呼ぶこと。
    """
    from mdx_cli.settings import get_settings

    return CredentialStore(config_dir=get_settings().config_dir)
