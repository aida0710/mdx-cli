import questionary
import typer
from rich.console import Console

from mdx_cli.api.endpoints.auth import sso_login
from mdx_cli.credentials.store import CredentialStore
from mdx_cli.settings import Settings

app = typer.Typer(help="認証管理")
console = Console()


def _get_store() -> CredentialStore:
    settings = Settings()
    return CredentialStore(config_dir=settings.config_dir)


@app.command()
def login() -> None:
    """MDX にログインする（Shibboleth SSO経由）"""
    store = _get_store()
    settings = Settings()

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
        console.print("[red]ログインに失敗しました。認証情報を確認してください。[/red]")
        raise typer.Exit(code=1)

    store.save_credentials(username, password)
    store.save_token(token)
    console.print(f"ログインしました（ユーザー: {username}）")


@app.command()
def logout() -> None:
    """ログアウトしてクレデンシャルを削除する"""
    store = _get_store()
    store.delete_token()
    store.delete_credentials()
    console.print("ログアウトしました")


@app.command()
def status() -> None:
    """認証状態を確認する"""
    store = _get_store()
    token = store.load_token()
    if token:
        creds = store.load_credentials()
        username = creds[0] if creds else "不明"
        console.print(f"ログイン済み（ユーザー: {username}）")
    else:
        console.print("ログインしていません")
