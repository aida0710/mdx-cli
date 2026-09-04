from typer.testing import CliRunner
from unittest.mock import patch

from mdx_cli.commands.auth import app

runner = CliRunner()

# RFC 6238 のテストベクタ用シークレット
TOTP_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def _sso_result_after_requesting_otp(token):
    def fake_sso_login(**kwargs):
        assert kwargs["otp"]()
        return token

    return fake_sso_login


def test_auth_login_success_new_user():
    with patch(
        "mdx_cli.commands.auth.sso_login",
        side_effect=_sso_result_after_requesting_otp("jwt-token-123"),
    ):
        with patch("mdx_cli.commands.auth.get_store") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = None
            store.load_totp_secret.return_value = None
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                mock_q.text.return_value.unsafe_ask.side_effect = ["user", "123456"]
                mock_q.password.return_value.unsafe_ask.return_value = "secret"
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 0
                assert "ログインしました" in result.output
                store.save_credentials.assert_called_once_with("user", "secret")
                store.save_token.assert_called_once_with("jwt-token-123")


def test_auth_login_success_saved_user():
    """保存済みID/PWがある場合、ユーザー名は確定表示してOTPだけ入力させる"""
    with patch(
        "mdx_cli.commands.auth.sso_login",
        side_effect=_sso_result_after_requesting_otp("jwt-token-456"),
    ):
        with patch("mdx_cli.commands.auth.get_store") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = ("saved_user", "saved_pass")
            store.load_totp_secret.return_value = None
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                mock_q.text.return_value.unsafe_ask.side_effect = ["123456"]
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 0
                assert "ログインしました" in result.output
                # 聞かれるのはOTPだけ（ユーザー名は保存済みのものを使う）
                assert mock_q.text.call_count == 1
                assert "OTP" in mock_q.text.call_args.args[0]
                mock_q.password.assert_not_called()


def test_auth_login_failure():
    with patch(
        "mdx_cli.commands.auth.sso_login",
        side_effect=_sso_result_after_requesting_otp(None),
    ):
        with patch("mdx_cli.commands.auth.get_store") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = None
            store.load_totp_secret.return_value = None
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                mock_q.text.return_value.unsafe_ask.side_effect = ["user", "000000"]
                mock_q.password.return_value.unsafe_ask.return_value = "wrong"
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 1
                assert "ログインに失敗しました" in result.output


def test_auth_status_not_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_token.return_value = None
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "ログインしていません" in result.output


def test_auth_status_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_token.return_value = "some-jwt-token"
        store.load_credentials.return_value = ("testuser", "testpass")
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "ログイン済み" in result.output


def test_auth_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("MDX_CONFIG_DIR", str(tmp_path))
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        store.delete_token.assert_called_once()
        store.delete_credentials.assert_called_once()


def test_auth_login_uses_saved_totp_secret():
    """TOTPシークレット登録済みなら、OTPを聞かずに自動生成してログインする"""
    with patch(
        "mdx_cli.commands.auth.sso_login",
        side_effect=_sso_result_after_requesting_otp("jwt-token-789"),
    ) as mock_sso:
        with patch("mdx_cli.commands.auth.get_store") as MockStore:
            store = MockStore.return_value
            store.load_credentials.return_value = ("saved_user", "saved_pass")
            store.load_totp_secret.return_value = ("saved_user", TOTP_SECRET)
            with patch("mdx_cli.commands.auth.questionary") as mock_q:
                result = runner.invoke(app, ["login"])
                assert result.exit_code == 0
                assert callable(mock_sso.call_args.kwargs["otp"])
                # ユーザー名もOTPも聞かずに完了する
                mock_q.text.assert_not_called()


def test_auth_otp_registers_secret():
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None
        with (
            patch("mdx_cli.commands.auth.questionary") as mock_q,
            patch("mdx_cli.commands.auth.verify_totp", return_value=True),
        ):
            mock_q.password.return_value.unsafe_ask.return_value = TOTP_SECRET
            mock_q.text.return_value.unsafe_ask.return_value = "123456"
            result = runner.invoke(app, ["otp"])
            assert result.exit_code == 0
            store.save_totp_secret.assert_called_once_with("saved_user", TOTP_SECRET)


def test_auth_otp_rejects_invalid_secret():
    """Base32として不正なシークレットは保存しない（ログイン時まで失敗を持ち越さない）"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            mock_q.password.return_value.unsafe_ask.return_value = "not-base32!"
            result = runner.invoke(app, ["otp"])
            assert result.exit_code == 1
            store.save_totp_secret.assert_not_called()


def test_auth_otp_delete():
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = ("saved_user", TOTP_SECRET)
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            mock_q.confirm.return_value.unsafe_ask.return_value = True
            result = runner.invoke(app, ["otp", "--delete"])
            assert result.exit_code == 0
            store.delete_totp_secret.assert_called_once()


def test_auth_otp_delete_when_not_registered():
    """未登録なら削除の確認も出さずに終わる"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            result = runner.invoke(app, ["otp", "--delete"])
            assert result.exit_code == 0
            assert "登録されていません" in result.output
            mock_q.confirm.assert_not_called()
            store.delete_totp_secret.assert_not_called()


def test_auth_otp_deletes_registered_secret_after_confirm():
    """登録済みの状態で mdx auth otp を実行すると、削除も選べる"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = ("saved_user", TOTP_SECRET)
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            mock_q.select.return_value.unsafe_ask.return_value = "delete"
            mock_q.confirm.return_value.unsafe_ask.return_value = True
            result = runner.invoke(app, ["otp"])
            assert result.exit_code == 0
            store.delete_totp_secret.assert_called_once()
            store.save_totp_secret.assert_not_called()


def test_auth_otp_delete_aborted_keeps_secret():
    """確認で No なら削除しない"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = ("saved_user", TOTP_SECRET)
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            mock_q.select.return_value.unsafe_ask.return_value = "delete"
            mock_q.confirm.return_value.unsafe_ask.return_value = False
            result = runner.invoke(app, ["otp"])
            assert result.exit_code != 0
            mock_q.select.assert_called_once()
            store.delete_totp_secret.assert_not_called()


def test_auth_otp_reregisters_when_already_registered():
    """登録済みでも登録し直せる"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = ("saved_user", "OLDSECRETOLDSECRE")
        with (
            patch("mdx_cli.commands.auth.questionary") as mock_q,
            patch("mdx_cli.commands.auth.verify_totp", return_value=True),
        ):
            mock_q.select.return_value.unsafe_ask.return_value = "register"
            mock_q.password.return_value.unsafe_ask.return_value = TOTP_SECRET
            mock_q.text.return_value.unsafe_ask.return_value = "123456"
            result = runner.invoke(app, ["otp"])
            assert result.exit_code == 0
            mock_q.select.assert_called_once()
            store.save_totp_secret.assert_called_once_with("saved_user", TOTP_SECRET)
            store.delete_totp_secret.assert_not_called()


def test_auth_otp_rejects_empty_secret():
    """空入力は保存しない（空Base32はデコードできてしまうため明示的に弾く）"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            mock_q.password.return_value.unsafe_ask.return_value = ""
            result = runner.invoke(app, ["otp"])
            assert result.exit_code == 1
            store.save_totp_secret.assert_not_called()


def test_auth_otp_requires_login():
    """未ログインでは登録できない（どのアカウントのシークレットか決まらないため）"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = None
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            result = runner.invoke(app, ["otp"])
            assert result.exit_code == 1
            assert "mdx auth login" in result.output
            mock_q.password.assert_not_called()
            store.save_totp_secret.assert_not_called()


def test_auth_otp_verifies_authenticator_code_without_printing_generated_otp():
    """登録確認は利用者のコードを照合し、生成したOTPを画面へ出さない。"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None
        with (
            patch("mdx_cli.commands.auth.questionary") as mock_q,
            patch("mdx_cli.commands.auth.generate_totp", return_value="654321"),
            patch("mdx_cli.commands.auth.verify_totp", return_value=True) as mock_verify,
        ):
            mock_q.password.return_value.unsafe_ask.return_value = TOTP_SECRET
            mock_q.text.return_value.unsafe_ask.return_value = "123456"

            result = runner.invoke(app, ["otp"])

    assert result.exit_code == 0
    mock_verify.assert_called_once_with(TOTP_SECRET, "123456")
    assert "654321" not in result.output
    store.save_totp_secret.assert_called_once_with("saved_user", TOTP_SECRET)


def test_auth_otp_rejects_mismatched_authenticator_code():
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None
        with (
            patch("mdx_cli.commands.auth.questionary") as mock_q,
            patch("mdx_cli.commands.auth.verify_totp", return_value=False),
        ):
            mock_q.password.return_value.unsafe_ask.return_value = TOTP_SECRET
            mock_q.text.return_value.unsafe_ask.return_value = "000000"

            result = runner.invoke(app, ["otp"])

    assert result.exit_code == 1
    assert "一致しません" in result.output
    store.save_totp_secret.assert_not_called()


def test_auth_otp_non_interactive_reads_secret_from_stdin():
    """raw modeを使えない端末では、リダイレクトした標準入力から登録できる。"""
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = None

        result = runner.invoke(app, ["otp", "--non-interactive"], input=f"{TOTP_SECRET}\n")

    assert result.exit_code == 0
    assert TOTP_SECRET not in result.output
    store.save_totp_secret.assert_called_once_with("saved_user", TOTP_SECRET)


def test_auth_otp_non_interactive_reregisters_without_questionary():
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = ("saved_user", "OLDSECRETOLDSECRE")
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            result = runner.invoke(app, ["otp", "--non-interactive"], input=f"{TOTP_SECRET}\n")

    assert result.exit_code == 0
    mock_q.select.assert_not_called()
    mock_q.password.assert_not_called()
    store.save_totp_secret.assert_called_once_with("saved_user", TOTP_SECRET)


def test_auth_otp_non_interactive_delete_needs_no_confirmation():
    with patch("mdx_cli.commands.auth.get_store") as MockStore:
        store = MockStore.return_value
        store.load_credentials.return_value = ("saved_user", "saved_pass")
        store.load_totp_secret.return_value = ("saved_user", TOTP_SECRET)
        with patch("mdx_cli.commands.auth.questionary") as mock_q:
            result = runner.invoke(app, ["otp", "--delete", "--non-interactive"])

    assert result.exit_code == 0
    mock_q.confirm.assert_not_called()
    store.delete_totp_secret.assert_called_once()


def test_read_non_interactive_secret_rejects_tty():
    import io

    import pytest

    from mdx_cli.commands.auth import _read_non_interactive_secret

    class TTYInput(io.StringIO):
        def isatty(self) -> bool:
            return True

    with pytest.raises(ValueError, match="リダイレクト"):
        _read_non_interactive_secret(TTYInput(TOTP_SECRET))
