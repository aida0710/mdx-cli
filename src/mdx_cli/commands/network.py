import json
from typing import NamedTuple

import questionary
import typer

from mdx_cli.api.endpoints.networks import (
    delete_acl,
    delete_dnat,
    get_segment_summary,
    list_acls,
    list_assignable_ips,
    list_dnats,
    list_segments,
)
from mdx_cli.api.endpoints.vms import list_vms
from mdx_cli.api.parallel import MAX_CONCURRENT_VM_DETAIL, parallel_get
from mdx_cli.api.spinner import progress_status, stop_active_spinner
from mdx_cli.commands._common import (
    get_auth_context,
    get_client,
    resolve_project_id,
    resolve_segment_id,
)
from mdx_cli.console import console, err_console
from mdx_cli.models.network import ACL
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import SEGMENT_COLUMNS, SEGMENT_SUMMARY_COLUMNS

from mdx_cli.commands.acl import app as acl_app
from mdx_cli.commands.dnat import app as dnat_app

app = typer.Typer(no_args_is_help=True, help="ネットワーク管理")
segment_app = typer.Typer(no_args_is_help=True, help="セグメント管理")
app.add_typer(segment_app, name="segment")
app.add_typer(acl_app, name="acl")
app.add_typer(dnat_app, name="dnat")


_INTERNAL_IP_PREFIX = "10.15."  # MDX内部ネットワーク。変更時はここだけ


class VmIpMaps(NamedTuple):
    global_ip_to_vm: dict[str, str]
    private_ip_to_vm: dict[str, str]
    partial_failure: bool


def _collect_vm_ip_maps(client, pid: str, json_mode: bool) -> VmIpMaps:
    """アクティブVMを並列取得し、IPマップを構築する。

    global_ip_to_vm: グローバルIP → "VM: <name>"
    private_ip_to_vm: プライベートIP → VM名
    partial_failure: VM詳細の並列取得で1台以上失敗したか
    """
    vms = list_vms(client, pid)
    stop_active_spinner()
    active_vms = [v for v in vms if v.status != "Deallocated"]

    token, base_url = get_auth_context()
    paths = [f"/api/vm/{v.uuid}/" for v in active_vms]
    with progress_status("VM詳細を取得中", len(active_vms), enabled=not json_mode) as progress:
        results = parallel_get(
            base_url, token, paths,
            max_concurrent=MAX_CONCURRENT_VM_DETAIL,
            on_progress=lambda idx: progress.advance(),
            return_exceptions=True,
        )

    global_ip_to_vm: dict[str, str] = {}
    private_ip_to_vm: dict[str, str] = {}
    partial_failure = False
    for v, data in zip(active_vms, results):
        if isinstance(data, Exception):
            partial_failure = True
            continue
        for net in data.get("service_networks", []):
            gip = net.get("global_ip", "")
            if gip:
                global_ip_to_vm[gip] = f"VM: {v.name}"
            for pip in net.get("ipv4_address", []):
                private_ip_to_vm[pip] = v.name
    return VmIpMaps(global_ip_to_vm, private_ip_to_vm, partial_failure)


def _is_host_mask(mask: str) -> bool:
    """単一ホスト指定のマスクか（255.255.255.255 / 32 / /32 形式に対応）。"""
    return mask.strip().lstrip("/") in ("255.255.255.255", "32")


def _collect_segment_acls(client, segments, json_mode: bool) -> list[list]:
    """各セグメントのACLを並列取得する（進捗表示付き）。

    戻り値は segments と同じ順序の ACL リストのリスト。
    100件超でページネーション継続があるセグメントは fetch_all で取り直す。
    取得に失敗したセグメントは空リストになる。
    """
    if not segments:
        return []
    token, base_url = get_auth_context()
    paths = [f"/api/acl/segment/{s.uuid}/?page_size=100" for s in segments]
    with progress_status("ACL取得中", len(segments), enabled=not json_mode) as progress:
        results = parallel_get(
            base_url, token, paths,
            on_progress=lambda idx: progress.advance(),
            return_exceptions=True,
        )

    acl_lists: list[list] = []
    needs_full: list[int] = []
    for i, raw in enumerate(results):
        if isinstance(raw, Exception):
            acl_lists.append([])
            continue
        if isinstance(raw, dict):
            acl_lists.append([ACL.model_validate(x) for x in raw.get("results", [])])
            if raw.get("next"):
                needs_full.append(i)
        elif isinstance(raw, list):
            acl_lists.append([ACL.model_validate(x) for x in raw])
        else:
            acl_lists.append([])
    # 100件超のセグメントは fetch_all で取り直し
    for i in needs_full:
        acl_lists[i] = list_acls(client, segments[i].uuid)
        stop_active_spinner()
    return acl_lists


@segment_app.command("list")
def segment_list(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """セグメント一覧"""
    client = get_client(silent=json)
    pid = resolve_project_id(project_id)
    segments = list_segments(client, pid)
    render(segments, SEGMENT_COLUMNS, json_mode=json)


@segment_app.command("show")
def segment_show(
    segment_id: str = typer.Argument(None, help="セグメントID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """セグメントサマリー（一覧から選択可能）"""
    client = get_client(silent=json)
    seg_id = resolve_segment_id(client, segment_id, project_id)
    summary = get_segment_summary(client, seg_id)
    render(summary, SEGMENT_SUMMARY_COLUMNS, json_mode=json)


@app.command("ips")
def ips_list(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json_mode: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """割当可能グローバルIP一覧"""
    import json

    client = get_client(silent=json_mode)
    pid = resolve_project_id(project_id)
    ips = list_assignable_ips(client, pid)
    stop_active_spinner()
    if json_mode:
        print(json.dumps(ips, indent=2))
    else:
        for ip in ips:
            console.print(ip)


@app.command("check-ip")
def check_ip(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json_mode: bool = typer.Option(False, "--json", help="JSON出力"),
    fix: bool = typer.Option(False, "--fix", help="死んだVM宛のDNATを削除"),
) -> None:
    """グローバルIPv4の使用状況を確認"""
    pid = resolve_project_id(project_id)
    client = get_client(silent=json_mode)

    # 割当可能IP（未使用）
    assignable = set(list_assignable_ips(client, pid))
    stop_active_spinner()

    # DNAT で使用中のIP
    dnats = list_dnats(client, pid)
    stop_active_spinner()

    # VM に直接割当されているIP
    vm_maps = _collect_vm_ip_maps(client, pid, json_mode)
    vm_map = vm_maps.global_ip_to_vm
    private_ip_to_vm = vm_maps.private_ip_to_vm

    # DNATの宛先IPからVM名を逆引き。死んだVM宛は穴として収集
    dnat_map: dict[str, str] = {}
    hole_dnats = []
    for d in dnats:
        vm_name = private_ip_to_vm.get(d.dst_address, "")
        if vm_name:
            dnat_map[d.pool_address] = f"DNAT → {d.dst_address} ({vm_name})"
        else:
            dnat_map[d.pool_address] = f"DNAT → {d.dst_address}"
            if d.dst_address.startswith(_INTERNAL_IP_PREFIX):
                hole_dnats.append(d)

    # 全IP を集約
    all_ips = sorted(assignable | set(dnat_map.keys()) | set(vm_map.keys()))

    if json_mode:
        result = []
        for ip in all_ips:
            status = "未使用"
            usage = ""
            if ip in vm_map:
                status = "VM割当"
                usage = vm_map[ip]
            elif ip in dnat_map:
                status = "DNAT"
                usage = dnat_map[ip]
            result.append({"ip": ip, "status": status, "usage": usage})
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        console.print("\n[bold]グローバルIPv4 使用状況:[/bold]\n")
        for ip in all_ips:
            if ip in vm_map:
                console.print(f"  {ip}  [cyan]{vm_map[ip]}[/cyan]")
            elif ip in dnat_map:
                console.print(f"  {ip}  [yellow]{dnat_map[ip]}[/yellow]")
            else:
                console.print(f"  {ip}  [green]未使用[/green]")

        used_count = sum(1 for ip in all_ips if ip in vm_map or ip in dnat_map)
        free_count = sum(1 for ip in all_ips if ip not in vm_map and ip not in dnat_map)
        console.print(f"\n  合計: {len(all_ips)}  使用中: {used_count}  未使用: {free_count}")
        console.print()

    if not hole_dnats:
        return

    # 穴の削除。--json 時のメッセージは stderr に出し、stdout のJSONを汚さない
    out = err_console if json_mode else console
    if not json_mode:
        console.print(f"\n[bold red]死んだVM宛のDNAT {len(hole_dnats)}件（穴）:[/bold red]")
        for d in hole_dnats:
            console.print(f"  {d.pool_address} → {d.dst_address} [dim]({d.uuid})[/dim]")
    if vm_maps.partial_failure:
        out.print("[yellow]⚠ VM詳細の取得に一部失敗しています。誤削除防止のため削除をスキップしました。再実行してください[/yellow]")
    elif fix or (not json_mode and questionary.confirm(f"{len(hole_dnats)}件を削除しますか？").unsafe_ask()):
        deleted, failed = 0, 0
        for d in hole_dnats:
            try:
                delete_dnat(client, d.uuid)
                deleted += 1
            except Exception as e:
                out.print(f"[red]  削除失敗 {d.uuid}: {e}[/red]")
                failed += 1
        stop_active_spinner()
        out.print(f"\n削除: {deleted}件  失敗: {failed}件")


@app.command("check-acl")
def check_acl(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json_mode: bool = typer.Option(False, "--json", help="JSON出力"),
    fix: bool = typer.Option(False, "--fix", help="死んだVM宛のACLを削除"),
) -> None:
    """ACLルールのうち存在しないVM宛の「穴」を検出する"""
    pid = resolve_project_id(project_id)
    client = get_client(silent=json_mode)

    vm_maps = _collect_vm_ip_maps(client, pid, json_mode)
    private_ip_to_vm = vm_maps.private_ip_to_vm

    segments = list_segments(client, pid)
    stop_active_spinner()

    acl_lists = _collect_segment_acls(client, segments, json_mode)

    # セグメントごとにACLを分類: [(segment, [(acl, status, vm_name), ...]), ...]
    seg_results: list = []
    holes: list = []  # (segment, acl) — 穴
    for seg, acls in zip(segments, acl_lists):
        classified: list = []
        for acl in acls:
            if not acl.dst_address.startswith(_INTERNAL_IP_PREFIX):
                continue  # 対象外（Any・外部IP）は表示しない
            if not _is_host_mask(acl.dst_mask):
                classified.append((acl, "range", None))
            elif acl.dst_address in private_ip_to_vm:
                classified.append((acl, "alive", private_ip_to_vm[acl.dst_address]))
            else:
                classified.append((acl, "hole", None))
                holes.append((seg, acl))
        if classified:
            seg_results.append((seg, classified))

    if json_mode:
        entries = []
        for seg, classified in seg_results:
            for acl, status, vm_name in classified:
                entries.append({
                    "segment_id": seg.uuid,
                    "segment_name": seg.name,
                    "acl_id": acl.uuid,
                    "protocol": acl.protocol,
                    "dst_address": acl.dst_address,
                    "dst_mask": acl.dst_mask,
                    "status": status,
                    "vm_name": vm_name,
                })
        print(json.dumps(entries, indent=2, ensure_ascii=False))
    else:
        console.print(f"\n[bold]ACL チェック（{_INTERNAL_IP_PREFIX}* 宛）:[/bold]")
        total_holes = 0
        for seg, classified in seg_results:
            console.print(f"\n[bold]セグメント: {seg.name}[/bold] [dim]({seg.uuid})[/dim]")
            for acl, status, vm_name in classified:
                line = (
                    f"{acl.protocol}  "
                    f"{acl.src_address}/{acl.src_mask} :{acl.src_port}  →  "
                    f"{acl.dst_address}/{acl.dst_mask} :{acl.dst_port}"
                )
                if status == "hole":
                    console.print(f"  [red]⚠ 穴 [/red] {line}  [red](VM不在)[/red]")
                elif status == "alive":
                    console.print(f"    生存 {line}  [dim](VM: {vm_name})[/dim]")
                else:
                    console.print(f"  [dim]  範囲 {line}[/dim]")
            h = sum(1 for _, s, _ in classified if s == "hole")
            a = sum(1 for _, s, _ in classified if s == "alive")
            r = sum(1 for _, s, _ in classified if s == "range")
            total_holes += h
            console.print(f"  [dim]合計: {len(classified)}  穴: {h}  生存: {a}  範囲: {r}[/dim]")
        console.print(f"\n  穴の総数: [bold red]{total_holes}[/bold red]\n")

    if not holes:
        return

    # 穴の削除。--json 時のメッセージは stderr に出し、stdout のJSONを汚さない
    out = err_console if json_mode else console
    if vm_maps.partial_failure:
        out.print("[yellow]⚠ VM詳細の取得に一部失敗しています。誤削除防止のため削除をスキップしました。再実行してください[/yellow]")
    elif fix or (not json_mode and questionary.confirm(f"{len(holes)}件の穴ACLを削除しますか？").unsafe_ask()):
        deleted, failed = 0, 0
        for seg, acl in holes:
            try:
                delete_acl(client, acl.uuid)
                deleted += 1
            except Exception as e:
                out.print(f"[red]  削除失敗 {acl.uuid}: {e}[/red]")
                failed += 1
        stop_active_spinner()
        out.print(f"\n削除: {deleted}件  失敗: {failed}件")
