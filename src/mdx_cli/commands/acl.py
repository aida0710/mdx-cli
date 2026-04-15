import questionary
from questionary import Choice
import typer
from rich.console import Console

from mdx_cli.api.endpoints.networks import (
    create_acl,
    delete_acl,
    list_acls,
    update_acl,
)
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import get_client, resolve_segment_id
from mdx_cli.models.network import ACLCreateRequest, ACLUpdateRequest
from mdx_cli.output.formatting import console, render
from mdx_cli.output.tables import ACL_COLUMNS
from mdx_cli.settings import Settings

app = typer.Typer(no_args_is_help=True, help="ACL管理")



@app.command("list")
def acl_list(
    segment_id: str = typer.Argument(None, help="セグメントID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ACL一覧"""
    client = get_client(silent=json)
    seg_id = resolve_segment_id(client, segment_id, project_id)
    acls = list_acls(client, seg_id)
    render(acls, ACL_COLUMNS, json_mode=json)


@app.command("add")
def acl_add(
    segment_id: str = typer.Argument(None, help="セグメントID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ACLルール追加（対話式）"""
    client = get_client(silent=json)
    seg_id = resolve_segment_id(client, segment_id, project_id)

    console.print("\n[bold]ACLルール追加[/bold]")
    protocol = questionary.select("プロトコル:", choices=["TCP", "UDP", "ICMP"]).unsafe_ask()
    src_address = questionary.text("送信元アドレス:", default="0.0.0.0").unsafe_ask()
    src_mask = questionary.text("送信元マスク:", default="0.0.0.0").unsafe_ask()
    src_port = "Any"
    if protocol != "ICMP":
        src_port = questionary.text("送信元ポート:", default="Any").unsafe_ask()
    dst_address = questionary.text("宛先アドレス:").unsafe_ask()
    dst_mask = questionary.text("宛先マスク:", default="255.255.255.255").unsafe_ask()
    dst_port = "Any"
    if protocol != "ICMP":
        dst_port = questionary.text("宛先ポート:", default="Any").unsafe_ask()

    console.print(f"\n[bold]確認:[/bold]")
    console.print(f"  プロトコル: {protocol}")
    console.print(f"  送信元:     {src_address}/{src_mask} :{src_port}")
    console.print(f"  宛先:       {dst_address}/{dst_mask} :{dst_port}")

    if not questionary.confirm("\n追加しますか？").unsafe_ask():
        raise typer.Abort()

    req = ACLCreateRequest(
        protocol=protocol,
        src_address=src_address,
        src_mask=src_mask,
        src_port=src_port,
        dst_address=dst_address,
        dst_mask=dst_mask,
        dst_port=dst_port,
        segment=seg_id,
    )
    acl = create_acl(client, req)
    render(acl, ACL_COLUMNS, json_mode=json)


@app.command("edit")
def acl_edit(
    acl_id: str = typer.Argument(None, help="ACL ID（省略時は一覧から選択）"),
    segment_id: str = typer.Option(None, "--segment-id", help="セグメントID（一覧表示用）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ACLルール編集（対話式）"""
    client = get_client(silent=json)

    # ACL ID が未指定なら一覧から選択
    if not acl_id:
        seg_id = resolve_segment_id(client, segment_id, project_id)
        acls = list_acls(client, seg_id)
        stop_active_spinner()

        if not acls:
            console.print("[yellow]ACLルールがありません[/yellow]")
            raise typer.Exit()

        console.print("\n[bold]ACL一覧:[/bold]")
        for i, a in enumerate(acls, 1):
            console.print(
                f"  {i}) [cyan]{a.protocol}[/cyan]"
                f"  {a.src_address}/{a.src_mask} :{a.src_port}"
                f"  →  {a.dst_address}/{a.dst_mask} :{a.dst_port}"
                f"  [dim]({a.uuid})[/dim]"
            )
        idx = int(questionary.text("\n編集する番号:").unsafe_ask()) - 1
        selected = acls[idx]
        acl_id = selected.uuid
    else:
        # IDから現在値を取得するにはlist経由で探す必要がある
        seg_id = resolve_segment_id(client, segment_id, project_id)
        acls = list_acls(client, seg_id)
        stop_active_spinner()
        selected = next((a for a in acls if a.uuid == acl_id), None)
        if not selected:
            console.print(f"[red]ACL {acl_id} が見つかりません[/red]")
            raise typer.Exit(code=1)

    # 現在値を表示して編集
    console.print(f"\n[bold]現在の値（Enterでそのまま）:[/bold]")
    protocol = questionary.select(
        "プロトコル:",
        choices=["TCP", "UDP", "ICMP"],
        default=selected.protocol,
    ).unsafe_ask()
    src_address = questionary.text("送信元アドレス:", default=selected.src_address).unsafe_ask()
    src_mask = questionary.text("送信元マスク:", default=selected.src_mask).unsafe_ask()
    src_port = selected.src_port
    if protocol != "ICMP":
        src_port = questionary.text("送信元ポート:", default=selected.src_port).unsafe_ask()
    dst_address = questionary.text("宛先アドレス:", default=selected.dst_address).unsafe_ask()
    dst_mask = questionary.text("宛先マスク:", default=selected.dst_mask).unsafe_ask()
    dst_port = selected.dst_port
    if protocol != "ICMP":
        dst_port = questionary.text("宛先ポート:", default=selected.dst_port).unsafe_ask()

    console.print(f"\n[bold]変更後:[/bold]")
    console.print(f"  プロトコル: {protocol}")
    console.print(f"  送信元:     {src_address}/{src_mask} :{src_port}")
    console.print(f"  宛先:       {dst_address}/{dst_mask} :{dst_port}")

    if not questionary.confirm("\n更新しますか？").unsafe_ask():
        raise typer.Abort()

    req = ACLUpdateRequest(
        protocol=protocol,
        src_address=src_address,
        src_mask=src_mask,
        src_port=src_port,
        dst_address=dst_address,
        dst_mask=dst_mask,
        dst_port=dst_port,
    )
    acl = update_acl(client, acl_id, req)
    render(acl, ACL_COLUMNS, json_mode=json)


@app.command("delete")
def acl_delete(
    acl_id: str = typer.Argument(None, help="ACL ID（省略時は一覧から選択）"),
    segment_id: str = typer.Option(None, "--segment-id", help="セグメントID（一覧表示用）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="確認をスキップ"),
) -> None:
    """ACLルール削除（一覧から選択可能）"""
    client = get_client()

    if not acl_id:
        seg_id = resolve_segment_id(client, segment_id, project_id)
        acls = list_acls(client, seg_id)
        stop_active_spinner()

        if not acls:
            console.print("[yellow]ACLルールがありません[/yellow]")
            raise typer.Exit()

        console.print("\n[bold]ACL一覧:[/bold]")
        for i, a in enumerate(acls, 1):
            console.print(
                f"  {i}) [cyan]{a.protocol}[/cyan]"
                f"  {a.src_address}/{a.src_mask} :{a.src_port}"
                f"  →  {a.dst_address}/{a.dst_mask} :{a.dst_port}"
                f"  [dim]({a.uuid})[/dim]"
            )
        idx = int(questionary.text("\n削除する番号:").unsafe_ask()) - 1
        acl_id = acls[idx].uuid

    if not yes:
        if not questionary.confirm(f"ACL {acl_id} を削除しますか？").unsafe_ask():
            raise typer.Abort()

    delete_acl(client, acl_id)
    stop_active_spinner()
    console.print(f"ACL {acl_id} を削除しました")
