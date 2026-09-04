import sys
from typing import TextIO

import questionary
import typer
from questionary import Choice

from mdx_cli.api.endpoints.auth import sso_login
from mdx_cli.commands._common import fail
from mdx_cli.console import console
from mdx_cli.credentials.store import get_store
from mdx_cli.credentials.totp import generate_totp, otp_from_store, verify_totp
from mdx_cli.settings import get_settings

app = typer.Typer(no_args_is_help=True, help="認証管理")


def _read_non_interactive_secret(stream: TextIO) -> str:
    """リダイレクトされた標準入力からTOTPシークレットを1行読む。"""
    if stream.isatty():
        raise ValueError("シークレットが画面に表示されないよう、標準入力をファイルまたはパイプからリダイレクトしてください")
    return stream.readline().strip()


@app.command()
def login() -> None:
    """MDX にログインする（Shibboleth SSO経由）"""
    store = get_store()
    settings = get_settings()

    # 保存済みID/PWがあればそのまま使う（別ユーザーに変えるときは logout してから）
    creds = store.load_credentials()
    if creds:
        username, password = creds
        console.print(f"ユーザー: [bold]{username}[/bold]")
        console.print("別のユーザーでログインする場合は `mdx auth logout` を実行してください", style="dim")
    else:
        username = questionary.text("ユーザー名:").unsafe_ask()
        password = questionary.password("パスワード:").unsafe_ask()

    def provide_otp() -> str:
        return otp_from_store(store, username) or questionary.text("OTP（ワンタイムパスワード）:").unsafe_ask()

    console.print("ログイン中...", style="dim")

    token = sso_login(
        base_url=settings.base_url,
        username=username,
        password=password,
        otp=provide_otp,
        timeout=settings.request_timeout,
    )

    if token is None:
        fail("ログインに失敗しました。認証情報を確認してください。")

    store.save_credentials(username, password)
    store.save_token(token)
    console.print(f"ログインしました（ユーザー: {username}）")


@app.command()
def otp(
    delete: bool = typer.Option(False, "--delete", help="登録済みシークレットを削除"),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="questionaryを使わず、シークレットを標準入力の先頭行から読む",
    ),
) -> None:
    """OTPの自動入力用にTOTPシークレットを登録する（登録済みなら削除も選べる）"""
    store = get_store()

    # シークレットはアカウントに紐付けて保存するため、ユーザー名が確定していないと登録できない
    creds = store.load_credentials()
    if not creds:
        fail("ログインしていません。先に `mdx auth login` を実行してください")
    username = creds[0]

    entry = store.load_totp_secret()

    if delete and not entry:
        console.print("TOTPシークレットは登録されていません")
        return

    if delete:
        action = "delete"
    elif non_interactive:
        action = "register"
    elif entry:
        action = questionary.select(
            f"TOTPシークレットは登録済みです（ユーザー: {entry[0]}）",
            choices=[
                Choice("登録し直す", value="register"),
                Choice("削除する（OTPは手入力に戻る）", value="delete"),
            ],
        ).unsafe_ask()
    else:
        action = "register"

    if action == "delete":
        if not non_interactive and not questionary.confirm(
            "削除するとログイン時にOTPの手入力が必要になります。削除しますか？"
        ).unsafe_ask():
            raise typer.Abort()
        store.delete_totp_secret()
        console.print("TOTPシークレットを削除しました")
        return

    if non_interactive:
        try:
            secret = _read_non_interactive_secret(sys.stdin)
        except ValueError as exc:
            fail(str(exc))
    else:
        secret = questionary.password(f"TOTPシークレット（Base32、ユーザー: {username}）:").unsafe_ask()
    if not secret or not secret.strip():
        fail("シークレットが入力されていません")
    try:
        generate_totp(secret)
    except ValueError:
        fail("シークレットが不正です（認証アプリに表示されるBase32文字列を入力してください）")

    if not non_interactive:
        code = questionary.text("認証アプリに表示されている現在のOTP:").unsafe_ask()
        if not verify_totp(secret, code):
            fail("認証アプリのOTPと一致しません。シークレットと端末時刻を確認してください")

    store.save_totp_secret(username, secret)
    console.print(f"TOTPシークレットを登録しました（ユーザー: {username}）")
    if non_interactive:
        console.print("次回のログインで自動生成したOTPを検証してください", style="dim")


@app.command()
def logout() -> None:
    """ログアウトしてクレデンシャルを削除する"""
    store = get_store()
    store.delete_token()
    store.delete_credentials()
    console.print("ログアウトしました")


@app.command()
def status() -> None:
    """認証状態を確認する"""
    store = get_store()
    token = store.load_token()
    if token:
        creds = store.load_credentials()
        username = creds[0] if creds else "不明"
        console.print(f"ログイン済み（ユーザー: {username}）")
    else:
        console.print("ログインしていません")
