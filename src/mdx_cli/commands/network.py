import typer

from mdx_cli.api.endpoints.networks import (
    get_segment_summary,
    list_assignable_ips,
    list_dnats,
    list_segments,
)
from mdx_cli.api.endpoints.vms import get_vm, list_vms
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import get_client, resolve_project_id, resolve_segment_id
from mdx_cli.output.formatting import console, render
from mdx_cli.output.tables import SEGMENT_COLUMNS, SEGMENT_SUMMARY_COLUMNS
from mdx_cli.settings import Settings

from mdx_cli.commands.acl import app as acl_app
from mdx_cli.commands.dnat import app as dnat_app

app = typer.Typer(help="ネットワーク管理")
segment_app = typer.Typer(help="セグメント管理")
app.add_typer(segment_app, name="segment")
app.add_typer(acl_app, name="acl")
app.add_typer(dnat_app, name="dnat")



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
) -> None:
    """グローバルIPv4の使用状況を確認"""
    import json

    pid = resolve_project_id(project_id)
    client = get_client(silent=json_mode)

    # 割当可能IP（未使用）
    assignable = set(list_assignable_ips(client, pid))
    stop_active_spinner()

    # DNAT で使用中のIP
    dnats = list_dnats(client, pid)
    stop_active_spinner()
    dnat_map: dict[str, str] = {}
    for d in dnats:
        dnat_map[d.pool_address] = f"DNAT → {d.dst_address}"

    # VM に直接割当されているIP（並列取得）
    vms = list_vms(client, pid)
    stop_active_spinner()
    active_vms = [v for v in vms if v.status != "Deallocated"]

    from mdx_cli.api.parallel import parallel_get
    from mdx_cli.api.spinner import _console as spin_console
    from mdx_cli.credentials.store import CredentialStore
    from rich.status import Status

    status_display = Status("", console=spin_console, spinner="dots") if not json_mode else None
    if status_display:
        status_display.start()
    done_count = 0

    def on_progress(idx: int) -> None:
        nonlocal done_count
        done_count += 1
        if status_display:
            status_display.update(f"VM詳細を取得中... ({done_count}/{len(active_vms)})")

    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    token = store.load_token() or ""
    paths = [f"/api/vm/{v.uuid}/" for v in active_vms]
    results = parallel_get(settings.base_url, token, paths, max_concurrent=10, on_progress=on_progress)
    if status_display:
        status_display.stop()

    vm_map: dict[str, str] = {}
    private_ip_to_vm: dict[str, str] = {}
    for v, data in zip(active_vms, results):
        for net in data.get("service_networks", []):
            gip = net.get("global_ip", "")
            if gip:
                vm_map[gip] = f"VM: {v.name}"
            for pip in net.get("ipv4_address", []):
                private_ip_to_vm[pip] = v.name

    # DNATの宛先IPからVM名を逆引き
    for pool_addr, label in list(dnat_map.items()):
        dst = label.split("→ ")[-1].strip()
        vm_name = private_ip_to_vm.get(dst, "")
        if vm_name:
            dnat_map[pool_addr] = f"DNAT → {dst} ({vm_name})"

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
        return

    console.print(f"\n[bold]グローバルIPv4 使用状況:[/bold]\n")
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
