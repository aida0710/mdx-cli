import questionary
import typer
from rich.console import Console

from mdx_cli.api.endpoints.networks import (
    create_dnat,
    delete_dnat,
    list_assignable_ips,
    list_dnats,
    update_dnat,
)
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import get_client, resolve_project_id, resolve_segment_id
from mdx_cli.models.network import DNATRequest
from mdx_cli.output.formatting import console, render
from mdx_cli.output.tables import DNAT_COLUMNS
from mdx_cli.settings import Settings

app = typer.Typer(no_args_is_help=True, help="DNAT管理")



@app.command("list")
def dnat_list(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """DNAT一覧"""
    pid = resolve_project_id(project_id)
    client = get_client(silent=json)
    dnats = list_dnats(client, pid)
    render(dnats, DNAT_COLUMNS, json_mode=json)


@app.command("add")
def dnat_add(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """DNATルール追加（対話式）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    # グローバルIP選択
    ips = list_assignable_ips(client, pid)
    stop_active_spinner()

    if not ips:
        console.print("[red]割当可能なグローバルIPがありません[/red]")
        raise typer.Exit(code=1)

    console.print("\n[bold]グローバルIP:[/bold]")
    for i, ip in enumerate(ips, 1):
        console.print(f"  {i}) {ip}")
    ip_idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
    pool_address = ips[ip_idx]

    # セグメント選択
    seg_id = resolve_segment_id(client, None, project_id)

    # 宛先アドレス
    dst_address = questionary.text("宛先アドレス（プライベートIP）:").unsafe_ask()

    console.print(f"\n[bold]確認:[/bold]")
    console.print(f"  グローバルIP: {pool_address}")
    console.print(f"  宛先:         {dst_address}")

    if not questionary.confirm("\n追加しますか？").unsafe_ask():
        raise typer.Abort()

    req = DNATRequest(
        pool_address=pool_address,
        segment=seg_id,
        dst_address=dst_address,
    )
    create_dnat(client, req)
    stop_active_spinner()
    console.print("[green]DNAT作成リクエストを受け付けました[/green]")


@app.command("edit")
def dnat_edit(
    dnat_id: str = typer.Argument(None, help="DNAT ID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """DNATルール編集（対話式）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    # DNAT選択
    dnats = list_dnats(client, pid)
    stop_active_spinner()

    if not dnats:
        console.print("[yellow]DNATルールがありません[/yellow]")
        raise typer.Exit()

    if not dnat_id:
        console.print("\n[bold]DNAT一覧:[/bold]")
        for i, d in enumerate(dnats, 1):
            console.print(f"  {i}) {d.pool_address} → {d.dst_address} [dim]({d.uuid})[/dim]")
        idx = int(questionary.text("\n編集する番号:").unsafe_ask()) - 1
        selected = dnats[idx]
        dnat_id = selected.uuid
    else:
        selected = next((d for d in dnats if d.uuid == dnat_id), None)
        if not selected:
            console.print(f"[red]DNAT {dnat_id} が見つかりません[/red]")
            raise typer.Exit(code=1)

    # グローバルIP選択
    ips = list_assignable_ips(client, pid)
    stop_active_spinner()
    # 現在のIPも選択肢に含める
    if selected.pool_address not in ips:
        ips.insert(0, selected.pool_address)

    console.print(f"\n[bold]現在の値（Enterでそのまま）:[/bold]")
    console.print(f"\n[bold]グローバルIP:[/bold]")
    for i, ip in enumerate(ips, 1):
        current = " [cyan](現在)[/cyan]" if ip == selected.pool_address else ""
        console.print(f"  {i}) {ip}{current}")
    default_ip_idx = str(ips.index(selected.pool_address) + 1)
    ip_idx = int(questionary.text("番号を入力:", default=default_ip_idx).unsafe_ask()) - 1
    pool_address = ips[ip_idx]

    # セグメント
    seg_id = resolve_segment_id(client, None, project_id)

    # 宛先アドレス
    dst_address = questionary.text("宛先アドレス:", default=selected.dst_address).unsafe_ask()

    console.print(f"\n[bold]変更後:[/bold]")
    console.print(f"  グローバルIP: {pool_address}")
    console.print(f"  宛先:         {dst_address}")

    if not questionary.confirm("\n更新しますか？").unsafe_ask():
        raise typer.Abort()

    req = DNATRequest(
        pool_address=pool_address,
        segment=seg_id,
        dst_address=dst_address,
    )
    update_dnat(client, dnat_id, req)
    stop_active_spinner()
    console.print("[green]DNAT更新リクエストを受け付けました[/green]")


@app.command("delete")
def dnat_delete(
    dnat_id: str = typer.Argument(None, help="DNAT ID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="確認をスキップ"),
) -> None:
    """DNATルール削除（一覧から選択可能）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    if not dnat_id:
        dnats = list_dnats(client, pid)
        stop_active_spinner()

        if not dnats:
            console.print("[yellow]DNATルールがありません[/yellow]")
            raise typer.Exit()

        console.print("\n[bold]DNAT一覧:[/bold]")
        for i, d in enumerate(dnats, 1):
            console.print(f"  {i}) {d.pool_address} → {d.dst_address} [dim]({d.uuid})[/dim]")
        idx = int(questionary.text("\n削除する番号:").unsafe_ask()) - 1
        dnat_id = dnats[idx].uuid

    if not yes:
        if not questionary.confirm(f"DNAT {dnat_id} を削除しますか？").unsafe_ask():
            raise typer.Abort()

    delete_dnat(client, dnat_id)
    stop_active_spinner()
    console.print(f"DNAT {dnat_id} の削除リクエストを受け付けました")
