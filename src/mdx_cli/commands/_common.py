"""コマンド共通ヘルパー"""

import re
from typing import Callable, NoReturn, Sequence, TypeVar

import questionary
import typer

from mdx_cli.api.auth import refresh_saved_token, token_needs_refresh
from mdx_cli.api.client import create_client
from mdx_cli.console import console, err_console
from mdx_cli.credentials.store import get_store
from mdx_cli.settings import get_settings

T = TypeVar("T")

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def is_uuid(value: str) -> bool:
    """ハイフン区切りの正規UUID形式か判定する。

    `len == 36 かつ "-" を含む` のような曖昧判定だと36文字のVM名を
    誤判定するため、形式を厳密にチェックする。
    """
    return bool(_UUID_RE.fullmatch(value))


def fail(message: str) -> NoReturn:
    """エラーを赤字で表示して終了コード1で抜ける。"""
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def get_client(silent: bool = False):
    """認証済みhttpxクライアントを取得する。

    トークンの期限が近い場合は事前リフレッシュして保存し、新トークンでクライアントを作る。
    リフレッシュ失敗時は既存トークンで続行（MDXAuth の 401 ハンドリングが保険）。
    """
    settings = get_settings()
    store = get_store()
    token = store.load_token()

    if token and token_needs_refresh(token):
        new_token = refresh_saved_token(token, settings.base_url)
        if new_token:
            store.save_token(new_token)
            token = new_token

    return create_client(token=token, silent=silent)


def get_auth_context() -> tuple[str, str]:
    """並列API（parallel_get/post/wait）用に (トークン, ベースURL) を返す。"""
    return get_store().load_token() or "", get_settings().base_url


def refresh_token_proactive() -> None:
    """バルク操作前にトークンを無条件リフレッシュして保存する。

    parallel_post は MDXAuth を経由しないため、チャンクごとに新鮮なトークンを
    取得しておく。失敗時は既存トークンで続行。
    """
    store = get_store()
    token = store.load_token()
    if not token:
        return

    new_token = refresh_saved_token(token, get_settings().base_url)
    if new_token:
        store.save_token(new_token)


def resolve_project_id(project_id: str | None) -> str:
    """プロジェクトIDを解決する。

    優先順位: 引数 > 保存済み > エラー
    """
    if project_id:
        return project_id

    saved = get_store().load_project_id()
    if saved:
        return saved

    raise typer.BadParameter(
        "プロジェクトIDが指定されていません。"
        "'mdx project select' で選択するか、--project-id で指定してください。"
    )


def prompt_int(
    label: str,
    max_val: int | None = None,
    default: str | None = None,
) -> int:
    """番号入力。非数値・0以下・範囲外はリトライする。"""
    while True:
        raw = questionary.text(label, default=default or "").unsafe_ask()
        try:
            val = int(raw)
        except ValueError:
            err_console.print("[red]数字を入力してください[/red]")
            continue
        if val < 1 or (max_val is not None and val > max_val):
            limit = f"1〜{max_val}" if max_val is not None else "1以上"
            err_console.print(f"[red]{limit} の範囲で入力してください[/red]")
            continue
        return val


def select_from_list(
    items: Sequence[T],
    formatter: Callable[[T], str],
    title: str | None = None,
    prompt: str = "番号を入力:",
    default: int | None = None,
) -> T:
    """一覧をRichで表示し、番号入力（1始まり）で1件選択する。

    formatter は要素を表示文字列（Richマークアップ可）に変換する。
    番号は prompt_int でバリデーションされ、不正入力はリトライになる。
    空リストは呼び出し側で先にチェックする契約（ValueError）。
    """
    if not items:
        raise ValueError("選択肢が空です")
    if title:
        console.print(f"\n[bold]{title}[/bold]")
    for i, item in enumerate(items, 1):
        console.print(f"  {i}) {formatter(item)}")
    idx = prompt_int(
        f"\n{prompt}",
        max_val=len(items),
        default=str(default) if default is not None else None,
    ) - 1
    return items[idx]


def resolve_segment_id(client, segment_id: str | None, project_id: str | None) -> str:
    """セグメントIDを解決する。指定があればそのまま、なければ一覧から選択。"""
    if segment_id:
        return segment_id

    from mdx_cli.api.endpoints.networks import list_segments
    from mdx_cli.api.spinner import stop_active_spinner

    pid = resolve_project_id(project_id)
    segments = list_segments(client, pid)
    stop_active_spinner()

    if not segments:
        fail("セグメントが見つかりません")
    if len(segments) == 1:
        console.print(f"セグメント: [bold]{segments[0].name}[/bold] (自動選択)")
        return segments[0].uuid

    selected = select_from_list(
        segments,
        lambda s: f"{s.name} [dim]({s.uuid})[/dim]",
        title="セグメント:",
    )
    return selected.uuid
