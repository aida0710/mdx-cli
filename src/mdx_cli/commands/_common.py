"""コマンド共通ヘルパー"""

import typer

from mdx_cli.api.client import create_client
from mdx_cli.credentials.store import CredentialStore
from mdx_cli.settings import Settings


def get_client(silent: bool = False):
    """認証済みhttpxクライアントを取得する。"""
    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    token = store.load_token()
    return create_client(token=token, silent=silent)


def resolve_project_id(project_id: str | None) -> str:
    """プロジェクトIDを解決する。

    優先順位: 引数 > 保存済み > エラー
    """
    if project_id:
        return project_id

    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    saved = store.load_project_id()
    if saved:
        return saved

    raise typer.BadParameter(
        "プロジェクトIDが指定されていません。"
        "'mdx project select' で選択するか、--project-id で指定してください。"
    )


def ask_or_abort(result):
    """questionary の .ask() 結果が None（Ctrl+C）なら Abort する。"""
    if result is None:
        raise typer.Abort()
    return result


def prompt_int(label: str, max_val: int | None = None) -> int:
    """番号入力。数字以外や範囲外でリトライする。"""
    import questionary
    while True:
        raw = questionary.text(label).unsafe_ask()
        try:
            val = int(raw)
        except ValueError:
            from rich.console import Console
            Console(stderr=True).print("[red]数字を入力してください[/red]")
            continue
        if max_val is not None and (val < 1 or val > max_val):
            from rich.console import Console
            Console(stderr=True).print(f"[red]1〜{max_val} の範囲で入力してください[/red]")
            continue
        return val


def resolve_segment_id(client, segment_id: str | None, project_id: str | None) -> str:
    """セグメントIDを解決する。指定があればそのまま、なければ一覧から選択。"""
    if segment_id:
        return segment_id

    import questionary
    from rich.console import Console
    from mdx_cli.api.endpoints.networks import list_segments
    from mdx_cli.api.spinner import stop_active_spinner

    console = Console()
    pid = resolve_project_id(project_id)
    segments = list_segments(client, pid)
    stop_active_spinner()

    if len(segments) == 1:
        console.print(f"セグメント: [bold]{segments[0].name}[/bold] (自動選択)")
        return segments[0].uuid

    console.print("\n[bold]セグメント:[/bold]")
    for i, s in enumerate(segments, 1):
        console.print(f"  {i}) {s.name} [dim]({s.uuid})[/dim]")
    idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
    return segments[idx].uuid
