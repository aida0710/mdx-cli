import questionary
import typer

from mdx_cli.api.endpoints.networks import (
    create_dnat,
    delete_dnat,
    list_assignable_ips,
    list_dnats,
    list_segments,
    update_dnat,
)
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import (
    fail,
    find_by_uuid,
    get_client,
    resolve_project_id,
    select_from_list,
    select_or_exit,
)
from mdx_cli.commands._prompt_steps import Step, ask, confirm_or_edit, run_steps
from mdx_cli.console import console
from mdx_cli.output.formatting import render
from mdx_cli.models.network import DNATRequest
from mdx_cli.output.tables import DNAT_COLUMNS

app = typer.Typer(no_args_is_help=True, help="DNAT管理")


def _format_dnat(d) -> str:
    return f"{d.pool_address} → {d.dst_address} [dim]({d.uuid})[/dim]"



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


def _dnat_steps(answers: dict, ips: list[str], segments: list, current_ip: str | None = None) -> list[Step]:
    """DNATの各項目を聞く手順（add / edit 共通）。answers の今の値を初期値にし、答えで上書きする。"""
    def default_number(items: list, value) -> int | None:
        return items.index(value) + 1 if value in items else None

    def ask_pool_address() -> None:
        answers["pool_address"] = select_from_list(
            ips,
            lambda ip: f"{ip} [cyan](現在)[/cyan]" if ip == current_ip else ip,
            title="グローバルIP:",
            default=default_number(ips, answers["pool_address"]),
        )

    def ask_segment() -> None:
        answers["segment"] = select_from_list(
            segments,
            lambda segment: f"{segment.name} [dim]({segment.uuid})[/dim]",
            title="セグメント:",
            default=default_number(segments, answers["segment"]),
        )

    def ask_dst_address() -> None:
        answers["dst_address"] = ask(questionary.text(
            "宛先アドレス（プライベートIP）:", default=answers["dst_address"]
        ))

    return [
        Step("グローバルIP", ask_pool_address),
        Step("セグメント", ask_segment, is_needed=lambda: len(segments) > 1),
        Step("宛先アドレス", ask_dst_address),
    ]


def _ask_dnat_request(answers: dict, steps: list[Step], header: str, message: str) -> DNATRequest:
    """各項目を聞き、内容を見せて「実行／直す／中止」を確認する。"""
    def print_summary() -> None:
        console.print(f"\n[bold]{header}[/bold]")
        console.print(f"  グローバルIP: {answers['pool_address']}")
        console.print(f"  セグメント:   {answers['segment'].name}")
        console.print(f"  宛先:         {answers['dst_address']}")

    run_steps(steps)
    confirm_or_edit(steps, print_summary=print_summary, message=message)
    return DNATRequest(
        pool_address=answers["pool_address"],
        segment=answers["segment"].uuid,
        dst_address=answers["dst_address"],
    )


def _list_segments_or_fail(client, pid: str) -> list:
    segments = list_segments(client, pid)
    stop_active_spinner()
    if not segments:
        fail("セグメントが見つかりません")
    return segments


@app.command("add")
def dnat_add(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """DNATルール追加（対話式。Esc で前の項目へ戻る）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    ips = list_assignable_ips(client, pid)
    stop_active_spinner()
    if not ips:
        fail("割当可能なグローバルIPがありません")
    segments = _list_segments_or_fail(client, pid)

    answers = {"pool_address": None, "segment": segments[0], "dst_address": ""}
    req = _ask_dnat_request(
        answers, _dnat_steps(answers, ips, segments), header="確認:", message="追加しますか？"
    )
    create_dnat(client, req)
    stop_active_spinner()
    console.print("[green]DNAT作成リクエストを受け付けました[/green]")


@app.command("edit")
def dnat_edit(
    dnat_id: str = typer.Argument(None, help="DNAT ID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """DNATルール編集（対話式。Esc で前の項目へ戻る）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    dnats = list_dnats(client, pid)
    stop_active_spinner()

    if not dnat_id:
        selected = select_or_exit(
            dnats, _format_dnat,
            title="DNAT一覧:", prompt="編集する番号:",
            empty_message="DNATルールがありません",
        )
        dnat_id = selected.uuid
    else:
        selected = find_by_uuid(dnats, dnat_id, label="DNAT")

    ips = list_assignable_ips(client, pid)
    stop_active_spinner()
    # 現在のIPも選択肢に含める
    if selected.pool_address not in ips:
        ips.insert(0, selected.pool_address)
    segments = _list_segments_or_fail(client, pid)
    # 一覧の応答の segment はセグメント名
    current_segment = next((s for s in segments if s.name == selected.segment), segments[0])

    console.print("\n[bold]現在の値（Enterでそのまま）:[/bold]")
    answers = {
        "pool_address": selected.pool_address,
        "segment": current_segment,
        "dst_address": selected.dst_address,
    }
    steps = _dnat_steps(answers, ips, segments, current_ip=selected.pool_address)
    req = _ask_dnat_request(answers, steps, header="変更後:", message="更新しますか？")
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

        selected = select_or_exit(
            dnats, _format_dnat,
            title="DNAT一覧:", prompt="削除する番号:",
            empty_message="DNATルールがありません",
        )
        dnat_id = selected.uuid

    if not yes:
        if not questionary.confirm(f"DNAT {dnat_id} を削除しますか？").unsafe_ask():
            raise typer.Abort()

    delete_dnat(client, dnat_id)
    stop_active_spinner()
    console.print(f"DNAT {dnat_id} の削除リクエストを受け付けました")
