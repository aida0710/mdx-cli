import typer

from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.api.endpoints.projects import (
    get_project_overview,
    get_project_storage,
    get_project_summary,
    list_access_keys,
    list_projects,
)
from mdx_cli.commands._common import fail, get_client, resolve_project_id, select_from_list
from mdx_cli.console import console
from mdx_cli.credentials.store import get_store
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import ACCESS_KEY_COLUMNS, PROJECT_COLUMNS

app = typer.Typer(no_args_is_help=True, help="プロジェクト管理")



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

    console.print("\n[bold]VM（スポット）:[/bold]")
    console.print(f"  [green]稼働中: {spot['power_on']}[/green]  停止: {spot['power_off']}  未割当: {spot['deallocated']}  合計: {spot['total']}")

    if guarantee["total"] > 0:
        console.print("\n[bold]VM（保証）:[/bold]")
        console.print(f"  [green]稼働中: {guarantee['power_on']}[/green]  停止: {guarantee['power_off']}  未割当: {guarantee['deallocated']}  合計: {guarantee['total']}")

    disk = resource.get("disk_size", {})
    used = disk.get("used", 0)
    unused = disk.get("unused", 0)
    total_disk = used + unused
    console.print("\n[bold]VMディスク:[/bold]")
    console.print(f"  使用: {used:.0f} GB / {total_disk:.0f} GB（残り {unused:.0f} GB）")

    cpu = resource.get("cpu_pack", {})
    gpu = resource.get("gpu_pack", {})
    if cpu.get("used", 0) > 0 or cpu.get("unused", 0) > 0:
        console.print("\n[bold]CPUパック:[/bold]")
        console.print(f"  使用: {cpu['used']}  未使用: {cpu['unused']}")
    if gpu.get("used", 0) > 0 or gpu.get("unused", 0) > 0:
        console.print("\n[bold]GPUパック:[/bold]")
        console.print(f"  使用: {gpu['used']}  未使用: {gpu['unused']}")

    # ストレージ情報
    st_extra = getattr(storage, "model_extra", {}) or {}

    def _parse_quota_value(value) -> tuple[int, bool]:
        """quota 値をパース。末尾 `*` はソフトリミット超過マーカー。"""
        if isinstance(value, (int, float)):
            return int(value), False
        s = str(value).strip()
        exceeded = s.endswith("*")
        if exceeded:
            s = s.rstrip("*")
        return (int(s) if s else 0), exceeded

    def _format_storage(label: str, data: dict) -> None:
        if not data:
            return
        kb_used, used_exceeded = _parse_quota_value(data.get("kbytes", 0))
        kb_limit, _ = _parse_quota_value(data.get("kbytes_limit", 0))
        fs = data.get("filesystem", "")
        warning = " [bold red]⚠ クオータ超過[/bold red]" if used_exceeded else ""
        if kb_limit > 0:
            gb_used = kb_used / 1024 / 1024
            gb_limit = kb_limit / 1024 / 1024
            gb_free = gb_limit - gb_used
            pct = (kb_used / kb_limit) * 100 if kb_limit else 0
            console.print(f"\n[bold]{label}:[/bold] [dim]{fs}[/dim]{warning}")
            console.print(f"  使用: {gb_used:,.1f} GB / {gb_limit:,.1f} GB（残り {gb_free:,.1f} GB, {pct:.1f}%）")
        elif kb_used > 0:
            gb_used = kb_used / 1024 / 1024
            console.print(f"\n[bold]{label}:[/bold] [dim]{fs}[/dim]{warning}")
            console.print(f"  使用: {gb_used:,.1f} GB")

    _format_storage("高速ストレージ", st_extra.get("high_speed_storage", {}))
    _format_storage("大容量ストレージ", st_extra.get("large_capacity_storage", {}))
    _format_storage("オブジェクトストレージ", st_extra.get("object_storage", {}))

    console.print()


@app.command("select")
def select_cmd() -> None:
    """使用するプロジェクトを選択して保存する"""
    store = get_store()
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
        fail("プロジェクトが見つかりません")

    current = store.load_project_id()
    if current:
        console.print(f"\n  現在の選択: [dim]{current}[/dim]")

    selected = select_from_list(
        all_projects,
        lambda p: f"{p.get('name', '')} [dim]({p.get('uuid', '')})[/dim]",
    )
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
