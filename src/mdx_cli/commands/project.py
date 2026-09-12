import json as json_lib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import typer
from click.core import ParameterSource
from rich.markup import escape

from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.api.endpoints.projects import (
    get_project_overview,
    get_project_overview_section,
    get_project_points,
    get_project_resource_usage,
    get_project_resources,
    get_project_storage,
    get_project_summary,
    list_access_keys,
    list_projects,
    list_project_users,
)
from mdx_cli.commands._common import fail, get_client, resolve_project_id, select_from_list
from mdx_cli.console import console
from mdx_cli.credentials.store import get_store
from mdx_cli.models.project import OverviewKind, Project, ReportLanguage
from mdx_cli.output.formatting import render, render_json
from mdx_cli.output.project import parse_usage_tables, render_fields, render_overview, render_resources, render_usage_tables
from mdx_cli.output.tables import (
    ACCESS_KEY_COLUMNS, PROJECT_COLUMNS, PROJECT_INFO_FIELDS, PROJECT_POINT_COLUMNS, PROJECT_USER_COLUMNS,
)

app = typer.Typer(no_args_is_help=True, help="プロジェクト管理")

ProjectOption = Annotated[str | None, typer.Option(
    "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID",
)]


def _flatten_projects(orgs) -> list[Project]:
    projects = []
    for org in orgs:
        nested = getattr(org, "projects", None)
        if nested is None:
            projects.append(org)
        else:
            for item in nested:
                project = Project.model_validate(item)
                projects.append(project.model_copy(update={"tenant": org.name}))
    return projects


@app.command("list")
def list_cmd(
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """アサイン済みプロジェクト一覧"""
    client = get_client(silent=json)
    projects = list_projects(client)
    if json:
        render_json(projects)
    else:
        render(_flatten_projects(projects), PROJECT_COLUMNS, json_mode=False)


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

    all_projects = _flatten_projects(orgs)

    stop_active_spinner()

    if not all_projects:
        fail("プロジェクトが見つかりません")

    current = store.load_project_id()
    if current:
        console.print(f"\n  現在の選択: [dim]{current}[/dim]")

    selected = select_from_list(
        all_projects,
        lambda p: f"{escape(p.name)} [dim]({escape(p.uuid)}) {escape(getattr(p, 'tenant', ''))}[/dim]",
    )
    store.save_project_id(selected.uuid)
    console.print(f"プロジェクトを選択しました: [bold]{escape(selected.name)}[/bold]")


@app.command()
def show(
    ctx: typer.Context,
    project_id: str | None = typer.Argument(None, help="プロジェクトID（省略時は選択済みを使用）"),
    project_option: ProjectOption = None,
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """プロジェクト情報（ID・名称・種別・申請者・利用期間）"""
    if (project_id and project_option and project_id != project_option
            and ctx.get_parameter_source("project_option") == ParameterSource.COMMANDLINE):
        raise typer.BadParameter("引数と --project-id に異なるIDが指定されています")
    pid = resolve_project_id(project_id or project_option)
    client = get_client(silent=json)
    summary = get_project_summary(client, pid)
    if json:
        render_json(summary)
    else:
        render_fields(summary.model_dump(), PROJECT_INFO_FIELDS)


@app.command("resources")
def resources_cmd(
    project_id: ProjectOption = None,
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """要求量・使用量・割当量・翌月割当量・Rminとストレージ等の資源情報"""
    pid = resolve_project_id(project_id)
    with get_client(silent=json) as client:
        resources = get_project_resources(client, pid)
    if json:
        render_json(resources)
    else:
        render_resources(resources.model_dump())


@app.command("users")
def users_cmd(
    project_id: ProjectOption = None,
    page: int | None = typer.Option(None, min=1, help="ページ番号（1始まり、省略時は全ページ取得）"),
    page_size: int = typer.Option(100, min=1, max=100, help="1リクエストあたりの件数"),
    ordering: str | None = typer.Option(None, help="ソート項目（例: --ordering=-username）"),
    username: str | None = typer.Option(None, help="ユーザー名フィルター（照合方法はサーバー依存）"),
    email: str | None = typer.Option(None, help="メールフィルター（照合方法はサーバー依存）"),
    auth: str | None = typer.Option(None, help="認証方式フィルター"),
    json: bool = typer.Option(False, "--json", help="総件数countとユーザー配列resultsをJSON出力"),
) -> None:
    """プロジェクトのユーザー一覧"""
    pid = resolve_project_id(project_id)
    with get_client(silent=json) as client:
        users = list_project_users(client, pid, page=page, page_size=page_size, ordering=ordering,
                                   username=username, email=email, auth=auth)
    if json:
        render_json(users)
    else:
        render(users.results, PROJECT_USER_COLUMNS, json_mode=False)
        console.print(f"総件数: {users.count}（表示: {len(users.results)}件）")


@app.command("points")
def points_cmd(
    project_id: ProjectOption = None,
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """購入・利用・残ポイントと利用期限"""
    pid = resolve_project_id(project_id)
    with get_client(silent=json) as client:
        points = get_project_points(client, pid)
    balance = points.total_remaining_points
    if json:
        stop_active_spinner()
        data = points.model_dump(mode="json")
        data["total_remaining_points"] = format(balance, "f") if balance is not None else None
        typer.echo(json_lib.dumps(data, ensure_ascii=False, indent=2))
    else:
        stop_active_spinner()
        if balance is None:
            console.print("合計残高: 算出できません（残ポイントが数値でない明細があります）", style="yellow")
        else:
            console.print(f"合計残高: {balance:,f} ポイント", style="bold green")
        console.print(f"最終消費処理日時: {points.lastConsumed or '—'}", markup=False)
        render(points.results, PROJECT_POINT_COLUMNS, json_mode=False)


def _usage_period(days: int | None, start: str | None, end: str | None, *, hours: int | None = None) -> dict:
    if hours is not None:
        if days is not None or start is not None or end is not None:
            raise typer.BadParameter("--hours は --days・--start・--end と併用できません")
        # APIは時単位の指定。OSのタイムゾーンによらずJSTの直近の正時で揃える。
        end_at = datetime.now(timezone(timedelta(hours=9), "JST")).replace(minute=0, second=0, microsecond=0)
        try:
            start_at = end_at - timedelta(hours=hours)
        except OverflowError:
            raise typer.BadParameter("--hours の値が大きすぎます")
        return {"input_type": 0, "start": start_at.strftime("%Y-%m-%d %H"), "end": end_at.strftime("%Y-%m-%d %H")}
    if start is not None or end is not None:
        if days is not None:
            raise typer.BadParameter("--days と --start/--end は併用できません")
        if start is None or end is None:
            raise typer.BadParameter("任意期間には --start と --end の両方が必要です")
        dates = []
        for name, value in [("--start", start), ("--end", end)]:
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}", value):
                    raise ValueError
                dates.append(datetime.strptime(value, "%Y-%m-%d %H"))
            except ValueError:
                raise typer.BadParameter(f'{name} は実在する日時を "YYYY-MM-DD HH"（00〜23時）で指定してください')
        if dates[0] >= dates[1]:
            raise typer.BadParameter("--end は --start より後の日時を指定してください")
        return {"input_type": 0, "start": start, "end": end}
    presets = {7: 1, 30: 2, 90: 3, 365: 4}
    if days is not None and days not in presets:
        raise typer.BadParameter("--days は 7・30・90・365 のいずれかを指定してください")
    return {"input_type": presets[days if days is not None else 7], "start": "", "end": ""}


@app.command("usage")
def usage_cmd(
    project_id: ProjectOption = None,
    days: int | None = typer.Option(None, help="最近7・30・90・365日（期間未指定時は7日）"),
    hours: int | None = typer.Option(None, min=1, help="直近の正時（JST）までの時間数（例: 24）"),
    start: str | None = typer.Option(None, help='期間開始 "YYYY-MM-DD HH"（タイムゾーン変換なし）'),
    end: str | None = typer.Option(None, help='期間終了 "YYYY-MM-DD HH"'),
    lang: ReportLanguage = typer.Option(ReportLanguage.jp, help="レポート言語: jp / en"),
    json: bool = typer.Option(False, "--json", help="元レスポンスと抽出したtablesをJSON出力"),
    html: bool = typer.Option(False, "--html", help="レポートHTMLを標準出力"),
    output: Path | None = typer.Option(None, "--output", "-o", dir_okay=False, help="レポートHTMLの保存先"),
) -> None:
    """指定期間の資源使用量・消費ポイント（閲覧用POST）"""
    params = _usage_period(days, start, end, hours=hours)
    if sum([json, html, output is not None]) > 1:
        raise typer.BadParameter("--json・--html・--output はいずれか1つを指定してください")
    pid = resolve_project_id(project_id)
    with get_client(silent=json or html) as client:
        report = get_project_resource_usage(client, pid, **params, lang=lang.value)
    stop_active_spinner()
    if report.err_msg:
        fail(escape(report.err_msg), stderr=True)
    if not report.html or not report.html.strip():
        fail("レポートHTMLが返されませんでした", stderr=True)
    if output is not None:
        try:
            output.write_text(report.html, encoding="utf-8")
        except OSError as exc:
            fail(escape(f"HTMLを保存できません: {exc}"), stderr=True)
        console.print(f"レポートHTMLを保存しました: {output}", markup=False)
    elif html:
        typer.echo(report.html, nl=False)
    else:
        tables = parse_usage_tables(report.html)
        if json:
            data = report.model_dump(mode="json")
            data["tables"] = [table.model_dump(mode="json") for table in tables]
            if hours is not None:
                data["period"] = {"start": params["start"], "end": params["end"], "hours": hours, "timezone": "JST"}
            typer.echo(json_lib.dumps(data, ensure_ascii=False, indent=2))
        elif tables:
            if hours is not None:
                console.print(f"対象期間: {params['start']}:00 ～ {params['end']}:00（{hours}時間・JST）")
            render_usage_tables(tables)
        else:
            fail("レポート内に表が見つかりません。--html または --output でHTMLを確認してください", stderr=True)


@app.command("overview")
def overview_cmd(
    project_id: ProjectOption = None,
    kind: OverviewKind = typer.Option(OverviewKind.all, help="取得する概要（既定: 全5種別）"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ダッシュボードの資源概要・一覧と専有／スポット／保証VM件数"""
    pid = resolve_project_id(project_id)
    with get_client(silent=json) as client:
        if kind == OverviewKind.all:
            data = {section.value: get_project_overview_section(client, pid, section.value)
                    for section in OverviewKind if section != OverviewKind.all}
        else:
            data = get_project_overview_section(client, pid, kind.value)
    stop_active_spinner()
    if json:
        typer.echo(json_lib.dumps(data, ensure_ascii=False, indent=2))
    else:
        render_overview(data if kind == OverviewKind.all else {kind.value: data})


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
