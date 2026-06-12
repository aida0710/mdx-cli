import questionary
import typer

from mdx_cli.api.endpoints.networks import (
    create_acl,
    delete_acl,
    list_acls,
    update_acl,
)
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import (
    find_by_uuid,
    get_client,
    resolve_segment_id,
    select_or_exit,
)
from mdx_cli.console import console
from mdx_cli.models.network import ACL, ACLCreateRequest, ACLUpdateRequest
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import ACL_COLUMNS

app = typer.Typer(no_args_is_help=True, help="ACL管理")


def _format_acl(a) -> str:
    return (
        f"[cyan]{a.protocol}[/cyan]"
        f"  {a.src_address}/{a.src_mask} :{a.src_port}"
        f"  →  {a.dst_address}/{a.dst_mask} :{a.dst_port}"
        f"  [dim]({a.uuid})[/dim]"
    )


def _prompt_acl_fields(selected: ACL | None = None) -> dict:
    """ACLルールの各フィールドを対話入力する（add / edit 共通）。

    selected があればその現在値を、なければ新規追加用の初期値をデフォルトにする。
    ICMP はポート概念がないためポート入力をスキップする。
    """
    protocol = questionary.select(
        "プロトコル:",
        choices=["TCP", "UDP", "ICMP"],
        default=selected.protocol if selected else None,
    ).unsafe_ask()
    src_address = questionary.text(
        "送信元アドレス:", default=selected.src_address if selected else "0.0.0.0"
    ).unsafe_ask()
    src_mask = questionary.text(
        "送信元マスク:", default=selected.src_mask if selected else "0.0.0.0"
    ).unsafe_ask()
    src_port = selected.src_port if selected else "Any"
    if protocol != "ICMP":
        src_port = questionary.text(
            "送信元ポート:", default=selected.src_port if selected else "Any"
        ).unsafe_ask()
    dst_address = questionary.text(
        "宛先アドレス:", default=selected.dst_address if selected else ""
    ).unsafe_ask()
    dst_mask = questionary.text(
        "宛先マスク:", default=selected.dst_mask if selected else "255.255.255.255"
    ).unsafe_ask()
    dst_port = selected.dst_port if selected else "Any"
    if protocol != "ICMP":
        dst_port = questionary.text(
            "宛先ポート:", default=selected.dst_port if selected else "Any"
        ).unsafe_ask()
    return {
        "protocol": protocol,
        "src_address": src_address,
        "src_mask": src_mask,
        "src_port": src_port,
        "dst_address": dst_address,
        "dst_mask": dst_mask,
        "dst_port": dst_port,
    }


def _print_acl_summary(header: str, fields: dict) -> None:
    console.print(f"\n[bold]{header}[/bold]")
    console.print(f"  プロトコル: {fields['protocol']}")
    console.print(f"  送信元:     {fields['src_address']}/{fields['src_mask']} :{fields['src_port']}")
    console.print(f"  宛先:       {fields['dst_address']}/{fields['dst_mask']} :{fields['dst_port']}")



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
    fields = _prompt_acl_fields()
    _print_acl_summary("確認:", fields)

    if not questionary.confirm("\n追加しますか？").unsafe_ask():
        raise typer.Abort()

    req = ACLCreateRequest(**fields, segment=seg_id)
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

    # IDから現在値を取得するにはlist経由で探す必要がある
    seg_id = resolve_segment_id(client, segment_id, project_id)
    acls = list_acls(client, seg_id)
    stop_active_spinner()

    if not acl_id:
        selected = select_or_exit(
            acls, _format_acl,
            title="ACL一覧:", prompt="編集する番号:",
            empty_message="ACLルールがありません",
        )
        acl_id = selected.uuid
    else:
        selected = find_by_uuid(acls, acl_id, label="ACL")

    # 現在値を表示して編集
    console.print("\n[bold]現在の値（Enterでそのまま）:[/bold]")
    fields = _prompt_acl_fields(selected)
    _print_acl_summary("変更後:", fields)

    if not questionary.confirm("\n更新しますか？").unsafe_ask():
        raise typer.Abort()

    req = ACLUpdateRequest(**fields)
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

        selected = select_or_exit(
            acls, _format_acl,
            title="ACL一覧:", prompt="削除する番号:",
            empty_message="ACLルールがありません",
        )
        acl_id = selected.uuid

    if not yes:
        if not questionary.confirm(f"ACL {acl_id} を削除しますか？").unsafe_ask():
            raise typer.Abort()

    delete_acl(client, acl_id)
    stop_active_spinner()
    console.print(f"ACL {acl_id} を削除しました")
