from typer.testing import CliRunner
from unittest.mock import patch, call

from mdx_cli.commands.auth import app

runner = CliRunner()


def test_auth_login_success_new_user():
    with patch("mdx_cli.commands.auth.sso_login", return_value="jwt-token-123"):
        with patch("mdx_cli.commands.auth.CredentialStore") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = None
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                mock_q.text.return_value.unsafe_ask.side_effect = ["user", "123456"]
                mock_q.password.return_value.unsafe_ask.return_value = "secret"
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 0
                assert "ログインしました" in result.output
                store.save_credentials.assert_called_once_with("user", "secret")
                store.save_token.assert_called_once_with("jwt-token-123")


def test_auth_login_success_saved_user():
    """保存済みID/PWがある場合、OTPだけ入力でログインできる"""
    with patch("mdx_cli.commands.auth.sso_login", return_value="jwt-token-456"):
        with patch("mdx_cli.commands.auth.CredentialStore") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = ("saved_user", "saved_pass")
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                # ユーザー名デフォルト確定 + OTP
                mock_q.text.return_value.unsafe_ask.side_effect = ["saved_user", "123456"]
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 0
                assert "ログインしました" in result.output


def test_auth_login_failure():
    with patch("mdx_cli.commands.auth.sso_login", return_value=None):
        with patch("mdx_cli.commands.auth.CredentialStore") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = None
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                mock_q.text.return_value.unsafe_ask.side_effect = ["user", "000000"]
                mock_q.password.return_value.unsafe_ask.return_value = "wrong"
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 1
                assert "ログインに失敗しました" in result.output


def test_auth_status_not_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands.auth.CredentialStore") as MockStore:
        store = MockStore.return_value
        store.load_token.return_value = None
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "ログインしていません" in result.output


def test_auth_status_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands.auth.CredentialStore") as MockStore:
        store = MockStore.return_value
        store.load_token.return_value = "some-jwt-token"
        store.load_credentials.return_value = ("testuser", "testpass")
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "ログイン済み" in result.output


def test_auth_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands.auth.CredentialStore") as MockStore:
        store = MockStore.return_value
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        store.delete_token.assert_called_once()
        store.delete_credentials.assert_called_once()
