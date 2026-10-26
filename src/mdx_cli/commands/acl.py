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
from mdx_cli.commands._prompt_steps import Step, ask, confirm_or_edit, run_steps
from mdx_cli.console import console
from mdx_cli.models.network import ACLCreateRequest, ACLUpdateRequest
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


# API はマスクをドット表記ではなくプレフィックス長で受け取る（"255.255.255.255" は 400）
_MAX_PREFIX_LENGTH = 32


def _validate_prefix_length(text: str) -> bool | str:
    if text.isdigit() and 0 <= int(text) <= _MAX_PREFIX_LENGTH:
        return True
    return f"0〜{_MAX_PREFIX_LENGTH}のプレフィックス長で入力してください（例: 32）"


# 新規追加の初期値。送信元はどこからでも、宛先は1台（/32）
_NEW_ACL_FIELDS = {
    "protocol": "TCP",
    "src_address": "0.0.0.0",
    "src_mask": "0",
    "src_port": "Any",
    "dst_address": "",
    "dst_mask": "32",
    "dst_port": "Any",
}


def _acl_field_steps(fields: dict) -> list[Step]:
    """ACLルールの各項目を聞く手順（add / edit 共通）。fields の今の値を初期値にし、答えで上書きする。

    ICMP はポートの概念がないのでポートを聞かない。
    """
    def ask_protocol() -> None:
        fields["protocol"] = ask(questionary.select(
            "プロトコル:", choices=["TCP", "UDP", "ICMP"], default=fields["protocol"]
        ))

    def ask_text(key: str, label: str, validate=None):
        def _ask() -> None:
            fields[key] = ask(questionary.text(label, default=fields[key], validate=validate))
        return _ask

    def has_ports() -> bool:
        return fields["protocol"] != "ICMP"

    return [
        Step("プロトコル", ask_protocol),
        Step("送信元アドレス", ask_text("src_address", "送信元アドレス:")),
        Step("送信元マスク", ask_text("src_mask", "送信元マスク（プレフィックス長）:", _validate_prefix_length)),
        Step("送信元ポート", ask_text("src_port", "送信元ポート:"), is_needed=has_ports),
        Step("宛先アドレス", ask_text("dst_address", "宛先アドレス:")),
        Step("宛先マスク", ask_text("dst_mask", "宛先マスク（プレフィックス長）:", _validate_prefix_length)),
        Step("宛先ポート", ask_text("dst_port", "宛先ポート:"), is_needed=has_ports),
    ]


def _ask_acl_fields(fields: dict, header: str, message: str) -> dict:
    """各項目を聞き、内容を見せて「実行／直す／中止」を確認する。送る値を返す。"""
    steps = _acl_field_steps(fields)
    run_steps(steps)
    confirm_or_edit(steps, print_summary=lambda: _print_acl_summary(header, fields), message=message)
    if fields["protocol"] == "ICMP":
        return {**fields, "src_port": "Any", "dst_port": "Any"}
    return dict(fields)


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
) -> None:
    """ACLルール追加（対話式）"""
    client = get_client()
    seg_id = resolve_segment_id(client, segment_id, project_id)

    console.print("\n[bold]ACLルール追加[/bold] [dim]（Esc で前の項目へ戻る）[/dim]")
    fields = _ask_acl_fields(dict(_NEW_ACL_FIELDS), header="確認:", message="追加しますか？")

    req = ACLCreateRequest(**fields, segment=seg_id)
    create_acl(client, req)
    stop_active_spinner()
    console.print("[green]ACL作成リクエストを受け付けました[/green]")


@app.command("edit")
def acl_edit(
    acl_id: str = typer.Argument(None, help="ACL ID（省略時は一覧から選択）"),
    segment_id: str = typer.Option(None, "--segment-id", help="セグメントID（一覧表示用）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """ACLルール編集（対話式）"""
    client = get_client()

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
    console.print("\n[bold]現在の値（Enterでそのまま、Esc で前の項目へ戻る）:[/bold]")
    current_fields = {key: getattr(selected, key) for key in _NEW_ACL_FIELDS}
    fields = _ask_acl_fields(current_fields, header="変更後:", message="更新しますか？")

    req = ACLUpdateRequest(**fields)
    update_acl(client, acl_id, req)
    stop_active_spinner()
    console.print("[green]ACL更新リクエストを受け付けました[/green]")


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
