import questionary
import typer

from mdx_cli.api.endpoints.auth import sso_login
from mdx_cli.commands._common import fail
from mdx_cli.console import console
from mdx_cli.credentials.store import get_store
from mdx_cli.settings import get_settings

app = typer.Typer(no_args_is_help=True, help="認証管理")


@app.command()
def login() -> None:
    """MDX にログインする（Shibboleth SSO経由）"""
    store = get_store()
    settings = get_settings()

    # 保存済みID/PWがあればデフォルトに
    creds = store.load_credentials()
    if creds:
        saved_user, saved_pass = creds
        console.print(f"保存済みユーザー: [bold]{saved_user}[/bold]")
        username = questionary.text("ユーザー名:", default=saved_user).unsafe_ask()
        if username == saved_user:
            password = saved_pass
        else:
            password = questionary.password("パスワード:").unsafe_ask()
    else:
        username = questionary.text("ユーザー名:").unsafe_ask()
        password = questionary.password("パスワード:").unsafe_ask()
    otp = questionary.text("OTP（ワンタイムパスワード）:").unsafe_ask()

    console.print("ログイン中...", style="dim")

    token = sso_login(
        base_url=settings.base_url,
        username=username,
        password=password,
        otp=otp,
        timeout=settings.request_timeout,
    )

    if token is None:
        fail("ログインに失敗しました。認証情報を確認してください。")

    store.save_credentials(username, password)
    store.save_token(token)
    console.print(f"ログインしました（ユーザー: {username}）")


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
