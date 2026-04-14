from mdx_cli.commands._common import get_client, resolve_project_id
import typer
from rich.console import Console

from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.api.endpoints.tasks import get_task, list_history, wait_for_task
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import HISTORY_COLUMNS, TASK_COLUMNS
from mdx_cli.settings import Settings

app = typer.Typer(help="タスク管理")
console = Console()


@app.command("list")
def list_cmd(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    limit: int = typer.Option(100, "--limit", "-n", help="取得件数（デフォルト100、最大1000）"),
    type_filter: str = typer.Option(None, "--type", "-t", help="操作種別フィルタ（例: デプロイ, 自動休止）"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """操作履歴一覧"""
    pid = resolve_project_id(project_id)
    limit = min(limit, 1000)
    client = get_client(silent=json)
    entries = list_history(client, pid, limit=limit, type_filter=type_filter)
    render(entries, HISTORY_COLUMNS, json_mode=json)


@app.command()
def status(
    task_id: str = typer.Argument(help="タスクID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """タスク状態確認"""
    client = get_client(silent=json)
    task = get_task(client, task_id)
    render(task, TASK_COLUMNS, json_mode=json)


@app.command()
def wait(
    task_id: str = typer.Argument(help="タスクID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """タスク完了まで待機"""
    client = get_client(silent=json)
    settings = Settings()
    stop_active_spinner()
    console.print(f"タスク {task_id} の完了を待機中...")
    task = wait_for_task(
        client,
        task_id,
        poll_interval=settings.task_poll_interval,
        timeout=settings.task_poll_timeout,
    )
    render(task, TASK_COLUMNS, json_mode=json)
