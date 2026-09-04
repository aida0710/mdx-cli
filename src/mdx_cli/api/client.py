import httpx

from mdx_cli.api.auth import MDXAuth
from mdx_cli.api.spinner import RequestSpinner
from mdx_cli.console import err_console
from mdx_cli.settings import Settings, get_settings


class MDXClient(httpx.Client):
    """スピナーを保持するhttpxクライアント。

    pagination 等がページ進捗をスピナーメッセージとして更新するために
    spinner を参照する。
    """

    def __init__(self, *args, spinner: RequestSpinner, **kwargs):
        super().__init__(*args, **kwargs)
        self.spinner = spinner


def _make_relogin_fn(settings: Settings):
    """保存済みID/PWと、登録済みならTOTPを使って再ログインする関数を返す。"""

    def relogin() -> str | None:
        from mdx_cli.api.endpoints.auth import sso_login
        from mdx_cli.credentials.store import get_store

        store = get_store()
        creds = store.load_credentials()
        if not creds:
            return None

        username, password = creds
        import questionary
        from mdx_cli.api.spinner import stop_active_spinner
        from mdx_cli.credentials.totp import otp_from_store

        stop_active_spinner()
        err_console.print(f"[yellow]セッション期限切れ。再ログインします（ユーザー: {username}）[/yellow]")

        def provide_otp() -> str:
            return otp_from_store(store, username) or questionary.text("OTP（ワンタイムパスワード）:").unsafe_ask()

        token = sso_login(
            base_url=settings.base_url,
            username=username,
            password=password,
            otp=provide_otp,
            timeout=settings.request_timeout,
        )
        if token:
            store.save_token(token)
            err_console.print("[green]再ログインしました[/green]")
        return token

    return relogin


def create_client(
    base_url: str | None = None,
    token: str | None = None,
    timeout: int | None = None,
    silent: bool = False,
) -> MDXClient:
    settings = get_settings()
    resolved_base_url = base_url or settings.base_url
    if not resolved_base_url.endswith("/"):
        resolved_base_url = resolved_base_url + "/"
    token_save_path = settings.config_dir / "token.json" if token else None
    relogin_fn = _make_relogin_fn(settings) if token else None

    spinner = RequestSpinner(silent=silent)

    return MDXClient(
        base_url=resolved_base_url,
        timeout=timeout or settings.request_timeout,
        auth=MDXAuth(token=token, token_save_path=token_save_path, relogin_fn=relogin_fn) if token else None,
        event_hooks=spinner.hooks(),
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        spinner=spinner,
    )
