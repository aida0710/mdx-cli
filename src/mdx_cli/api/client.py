import httpx
import typer
from rich.console import Console

from mdx_cli.api.auth import MDXAuth
from mdx_cli.api.spinner import RequestSpinner
from mdx_cli.settings import Settings

_console = Console(stderr=True)


def _make_relogin_fn(settings: Settings):
    """保存済みID/PWを使い、OTPだけプロンプトして再ログインする関数を返す。"""
    def relogin() -> str | None:
        from mdx_cli.api.endpoints.auth import sso_login
        from mdx_cli.credentials.store import CredentialStore

        store = CredentialStore(config_dir=settings.config_dir)
        creds = store.load_credentials()
        if not creds:
            return None

        username, password = creds
        import questionary
        from mdx_cli.api.spinner import stop_active_spinner
        stop_active_spinner()
        _console.print(f"[yellow]セッション期限切れ。再ログインします（ユーザー: {username}）[/yellow]")
        otp = questionary.text("OTP（ワンタイムパスワード）:").unsafe_ask()

        token = sso_login(
            base_url=settings.base_url,
            username=username,
            password=password,
            otp=otp,
            timeout=settings.request_timeout,
        )
        if token:
            store.save_token(token)
            _console.print("[green]再ログインしました[/green]")
        return token

    return relogin


def create_client(
    base_url: str | None = None,
    token: str | None = None,
    timeout: int | None = None,
    silent: bool = False,
) -> httpx.Client:
    settings = Settings()
    resolved_base_url = base_url or settings.base_url
    if not resolved_base_url.endswith("/"):
        resolved_base_url = resolved_base_url + "/"
    token_save_path = settings.config_dir / "token.json" if token else None
    relogin_fn = _make_relogin_fn(settings) if token else None

    spinner = RequestSpinner(silent=silent)

    client = httpx.Client(
        base_url=resolved_base_url,
        timeout=timeout or settings.request_timeout,
        auth=MDXAuth(token=token, token_save_path=token_save_path, relogin_fn=relogin_fn) if token else None,
        event_hooks=spinner.hooks(),
    )
    # スピナーインスタンスをクライアントに保持（ページネーション進捗更新用）
    client._spinner = spinner  # type: ignore[attr-defined]
    return client
