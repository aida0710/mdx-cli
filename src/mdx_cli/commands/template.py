import questionary
import typer
from rich.console import Console

from mdx_cli.api.endpoints.templates import list_templates
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import get_client, resolve_project_id
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import TEMPLATE_COLUMNS
from mdx_cli.settings import Settings

app = typer.Typer(help="テンプレート管理")
console = Console()



@app.command("list")
def list_cmd(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """テンプレート一覧"""
    client = get_client(silent=json)
    pid = resolve_project_id(project_id)
    templates = list_templates(client, pid)
    render(templates, TEMPLATE_COLUMNS, json_mode=json)


@app.command("show")
def show_cmd(
    template_id: str = typer.Argument(None, help="テンプレートID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """テンプレート詳細"""
    client = get_client(silent=json)
    pid = resolve_project_id(project_id)
    templates = list_templates(client, pid)
    stop_active_spinner()

    if template_id:
        selected = next((t for t in templates if t.uuid == template_id), None)
    else:
        console.print("\n[bold]テンプレート:[/bold]")
        for i, t in enumerate(templates, 1):
            os_info = f" [cyan]{t.os_name or ''} {t.os_version or ''}[/cyan]" if t.os_name else ""
            console.print(f"  {i}) {t.name}{os_info}")
        idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
        selected = templates[idx]

    if not selected:
        console.print("[red]テンプレートが見つかりません[/red]")
        raise typer.Exit(code=1)

    if json:
        from mdx_cli.output.formatting import render_json
        render_json(selected)
        return

    extra = getattr(selected, "model_extra", {}) or {}
    console.print(f"\n[bold]{selected.name}[/bold]")
    console.print(f"  UUID:             {selected.uuid}")
    console.print(f"  テンプレート名:   {selected.template_name or '-'}")
    console.print(f"  OS:               {selected.os_name or '-'} {selected.os_version or ''}")
    console.print(f"  OSタイプ:         {selected.os_type or '-'}")
    console.print(f"  GPU必須:          {selected.gpu_required}")
    console.print(f"  最小ディスク:     {selected.lower_limit_disk} GB")
    console.print(f"  最小メモリ:       {extra.get('lower_limit_memory', '-')} GB")
    console.print(f"  HWバージョン:     {extra.get('hw_version', '-')}")
    console.print(f"  ログインユーザー: {selected.login_username or '-'}")
    console.print(f"  説明:             {selected.description or '-'}")
    console.print(f"  制作:             {extra.get('create_tenant_name', '-')}")
    console.print(f"  公開日:           {extra.get('create_date_str', '-')}")
    console.print(f"  公開範囲:         {extra.get('scope', '-')}")
    url = extra.get("summary_url", "")
    if url:
        console.print(f"  ドキュメント:     {url}")
    console.print()
