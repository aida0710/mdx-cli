import questionary
from questionary import Choice
import typer
from rich.console import Console

from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.api.endpoints.projects import (
    get_project_overview,
    get_project_storage,
    get_project_summary,
    list_access_keys,
    list_projects,
)
from mdx_cli.commands._common import get_client, resolve_project_id
from mdx_cli.credentials.store import CredentialStore
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import ACCESS_KEY_COLUMNS, PROJECT_COLUMNS
from mdx_cli.settings import Settings

app = typer.Typer(no_args_is_help=True, help="プロジェクト管理")
console = Console()



@app.command("list")
def list_cmd(
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """アサイン済みプロジェクト一覧"""
    client = get_client(silent=json)
    projects = list_projects(client)
    render(projects, PROJECT_COLUMNS, json_mode=json)


@app.command("summary")
def summary_cmd(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json_mode: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """プロジェクト概要（VM数・リソース・ストレージ使用量）"""
    import json as json_lib
    pid = resolve_project_id(project_id)
    client = get_client(silent=json_mode)
    overview = get_project_overview(client, pid)
    storage = get_project_storage(client, pid)
    stop_active_spinner()

    if json_mode:
        overview["storage"] = storage.model_dump(mode="json") if hasattr(storage, "model_dump") else storage
        print(json_lib.dumps(overview, indent=2, ensure_ascii=False))
        return

    spot = overview["spot_vm"]
    guarantee = overview["guarantee_vm"]
    resource = overview["resource"]

    console.print(f"\n[bold]VM（スポット）:[/bold]")
    console.print(f"  [green]稼働中: {spot['power_on']}[/green]  停止: {spot['power_off']}  未割当: {spot['deallocated']}  合計: {spot['total']}")

    if guarantee["total"] > 0:
        console.print(f"\n[bold]VM（保証）:[/bold]")
        console.print(f"  [green]稼働中: {guarantee['power_on']}[/green]  停止: {guarantee['power_off']}  未割当: {guarantee['deallocated']}  合計: {guarantee['total']}")

    disk = resource.get("disk_size", {})
    used = disk.get("used", 0)
    unused = disk.get("unused", 0)
    total_disk = used + unused
    console.print(f"\n[bold]VMディスク:[/bold]")
    console.print(f"  使用: {used:.0f} GB / {total_disk:.0f} GB（残り {unused:.0f} GB）")

    cpu = resource.get("cpu_pack", {})
    gpu = resource.get("gpu_pack", {})
    if cpu.get("used", 0) > 0 or cpu.get("unused", 0) > 0:
        console.print(f"\n[bold]CPUパック:[/bold]")
        console.print(f"  使用: {cpu['used']}  未使用: {cpu['unused']}")
    if gpu.get("used", 0) > 0 or gpu.get("unused", 0) > 0:
        console.print(f"\n[bold]GPUパック:[/bold]")
        console.print(f"  使用: {gpu['used']}  未使用: {gpu['unused']}")

    # ストレージ情報
    st_extra = getattr(storage, "model_extra", {}) or {}

    def _format_storage(label: str, data: dict) -> None:
        if not data:
            return
        kb_used = int(data.get("kbytes", 0))
        kb_limit = int(data.get("kbytes_limit", 0))
        fs = data.get("filesystem", "")
        if kb_limit > 0:
            gb_used = kb_used / 1024 / 1024
            gb_limit = kb_limit / 1024 / 1024
            gb_free = gb_limit - gb_used
            pct = (kb_used / kb_limit) * 100 if kb_limit else 0
            console.print(f"\n[bold]{label}:[/bold] [dim]{fs}[/dim]")
            console.print(f"  使用: {gb_used:,.1f} GB / {gb_limit:,.1f} GB（残り {gb_free:,.1f} GB, {pct:.1f}%）")
        elif kb_used > 0:
            gb_used = kb_used / 1024 / 1024
            console.print(f"\n[bold]{label}:[/bold] [dim]{fs}[/dim]")
            console.print(f"  使用: {gb_used:,.1f} GB")

    _format_storage("高速ストレージ", st_extra.get("high_speed_storage", {}))
    _format_storage("大容量ストレージ", st_extra.get("large_capacity_storage", {}))
    _format_storage("オブジェクトストレージ", st_extra.get("object_storage", {}))

    console.print()


@app.command("select")
def select_cmd() -> None:
    """使用するプロジェクトを選択して保存する"""
    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    client = get_client()
    orgs = list_projects(client)

    # 組織内のプロジェクトをフラットに展開
    all_projects: list[dict] = []
    for org in orgs:
        nested = org.model_extra.get("projects", []) if hasattr(org, "model_extra") else []
        for proj in nested:
            all_projects.append(proj)
        # ネストがなければ組織自体をプロジェクトとして扱う
        if not nested:
            all_projects.append({"uuid": org.uuid, "name": org.name})

    stop_active_spinner()

    if not all_projects:
        console.print("[red]プロジェクトが見つかりません[/red]")
        raise typer.Exit(code=1)

    console.print()
    for i, proj in enumerate(all_projects, 1):
        name = proj.get("name", "")
        uuid = proj.get("uuid", "")
        console.print(f"  [bold]{i}[/bold]) {name} [dim]({uuid})[/dim]")
    console.print()

    current = store.load_project_id()
    if current:
        console.print(f"  現在の選択: [dim]{current}[/dim]")

    choice = int(questionary.text("番号を入力:").unsafe_ask())
    if choice < 1 or choice > len(all_projects):
        console.print("[red]無効な番号です[/red]")
        raise typer.Exit(code=1)

    selected = all_projects[choice - 1]
    store.save_project_id(selected["uuid"])
    console.print(f"プロジェクトを選択しました: [bold]{selected['name']}[/bold]")


@app.command()
def show(
    project_id: str = typer.Argument(help="プロジェクトID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """プロジェクトサマリー"""
    client = get_client(silent=json)
    summary = get_project_summary(client, project_id)
    render(summary, PROJECT_COLUMNS, json_mode=json)


@app.command()
def storage(
    project_id: str = typer.Argument(help="プロジェクトID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ストレージ情報"""
    client = get_client(silent=json)
    info = get_project_storage(client, project_id)
    render(info, [("UUID", "uuid"), ("名前", "name")], json_mode=json)


@app.command()
def keys(
    project_id: str = typer.Argument(help="プロジェクトID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """アクセスキー一覧"""
    client = get_client(silent=json)
    access_keys = list_access_keys(client, project_id)
    render(access_keys, ACCESS_KEY_COLUMNS, json_mode=json)
