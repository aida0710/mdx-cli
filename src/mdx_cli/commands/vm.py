from pathlib import Path

import httpx
import questionary
from questionary import Choice
import typer

from mdx_cli.api.endpoints.networks import list_segments
from mdx_cli.api.endpoints.templates import list_templates
from mdx_cli.api.endpoints.vms import (
    deploy_vm,
    get_vm,
    list_vms,
    reconfigure_vm,
    sync_vms,
    vm_action_path,
)
from mdx_cli.api.parallel import parallel_post, parallel_wait
from mdx_cli.api.spinner import progress_status, stop_active_spinner
from mdx_cli.commands._common import (
    fail,
    get_auth_context,
    get_client,
    is_uuid,
    prompt_int,
    refresh_token_proactive,
    resolve_project_id,
    select_from_list,
)
from mdx_cli.commands._deploy_plan import DeployPlan
from mdx_cli.commands._name_pattern import (
    expand_name_pattern,
    expand_name_pattern_for_deploy,
    match_names,
)
from mdx_cli.console import console
from mdx_cli.models.pack import PACK_SPECS
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import VM_COLUMNS
from mdx_cli.settings import get_settings

app = typer.Typer(no_args_is_help=True, help="仮想マシン管理")



@app.command("list")
def list_cmd(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """VM一覧"""
    pid = resolve_project_id(project_id)
    client = get_client(silent=json)
    vms = list_vms(client, pid)
    render(vms, VM_COLUMNS, json_mode=json)


@app.command()
def show(
    target: str = typer.Argument(None, help="VM ID または名前（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """VM詳細"""
    client = get_client(silent=json)

    # UUID指定
    if target and is_uuid(target):
        vm = get_vm(client, target)
    elif target:
        # 名前で検索
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        matched = [v for v in all_vms if v.name == target]
        if not matched:
            fail(f"VM '{target}' が見つかりません")
        vm = get_vm(client, matched[0].uuid)
    else:
        # 一覧から選択
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        if not all_vms:
            fail("VMがありません")
        selected = select_from_list(
            all_vms, lambda v: f"{v.name} [{v.status}]", title="VM一覧:"
        )
        vm = get_vm(client, selected.uuid)

    stop_active_spinner()

    if json:
        from mdx_cli.output.formatting import render_json
        render_json(vm)
        return

    # Rich表示
    extra = getattr(vm, "model_extra", {}) or {}
    console.print(f"\n[bold]{vm.name}[/bold]")
    console.print(f"  UUID:           {vm.uuid}")
    console.print(f"  状態:           {vm.status}")
    console.print(f"  サービスレベル: {vm.service_level}")
    console.print(f"  OS:             {extra.get('os_type', '-')}")
    console.print(f"  CPU:            {extra.get('cpu', '-')}")
    console.print(f"  メモリ:         {extra.get('memory', '-')}")
    console.print(f"  GPU:            {extra.get('gpu', '-')}")
    console.print(f"  パック:         {vm.pack_type or '-'} x {vm.pack_num if vm.pack_num is not None else '-'}")
    console.print(f"  NVLink:         {extra.get('nvlink', '-')}")

    # ディスク
    disks = vm.hard_disks
    if disks:
        console.print("\n[bold]ディスク:[/bold]")
        for d in disks:
            console.print(f"  #{d.get('disk_number', '?')}: {d.get('capacity', '?')} ({d.get('datastore', '')})")

    # ネットワーク
    nets = vm.service_networks
    if nets:
        console.print("\n[bold]ネットワーク:[/bold]")
        for n in nets:
            ipv4 = ", ".join(n.get("ipv4_address", []))
            gip = n.get("global_ip", "")
            seg = n.get("segment", "")
            console.print(f"  アダプタ {n.get('adapter_number', '?')}:")
            console.print(f"    セグメント:   {seg}")
            console.print(f"    IPv4:         {ipv4}")
            if gip:
                console.print(f"    グローバルIP: {gip}")

    # ストレージネットワーク
    snets = vm.storage_networks
    if snets:
        console.print("\n[bold]ストレージネットワーク:[/bold]")
        for sn in snets:
            ipv4 = ", ".join(sn.get("ipv4_address", []))
            console.print(f"  アダプタ {sn.get('adapter_number', '?')}: {ipv4} ({sn.get('storage_network_type', '')})")

    # VMware Tools
    tools = extra.get("vmware_tools", {})
    if tools:
        console.print("\n[bold]VMware Tools:[/bold]")
        console.print(f"  状態:     {tools.get('status', '-')}")
        console.print(f"  バージョン: {tools.get('version', '-')}")

    console.print()


def _list_pubkeys() -> list[Path]:
    """~/.ssh にある公開鍵(.pub)の一覧を返す。標準的な鍵名を優先して並べる。"""
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.is_dir():
        return []
    priority = {"id_ed25519.pub": 0, "id_rsa.pub": 1, "id_ecdsa.pub": 2}
    return sorted(
        ssh_dir.glob("*.pub"),
        key=lambda p: (priority.get(p.name, 99), p.name),
    )


def _pubkey_preview(path: Path) -> str:
    """公開鍵ファイル内容のプレビュー（先頭30文字...末尾30文字）。"""
    try:
        content = path.read_text().strip()
    except OSError:
        return "(読み取り不可)"
    if len(content) <= 63:
        return content
    return f"{content[:30]}...{content[-30:]}"


@app.command()
def deploy(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    template: str = typer.Option(None, "--template", "-t", help="テンプレート名（部分一致）"),
    name: str = typer.Option(None, "--name", "-n", help="VM名（パターン対応: name-{0-9}）"),
    pack_type_opt: str = typer.Option(None, "--pack-type", help="cpu / gpu"),
    pack_num_opt: int = typer.Option(None, "--pack-num", help="パック数"),
    disk: int = typer.Option(None, "--disk", help="ディスクサイズ(GB)"),
    service_level_opt: str = typer.Option(None, "--service-level", help="spot / guarantee"),
    key: str = typer.Option(None, "--key", "-k", help="SSH公開鍵のパス"),
    power_on: bool = typer.Option(False, "--power-on", help="デプロイ後に自動起動"),
    yes: bool = typer.Option(False, "--yes", "-y", help="確認をスキップ"),
    no_wait: bool = typer.Option(False, "--no-wait", help="タスク完了を待たない"),
) -> None:
    """VMデプロイ（対話式 / 全引数指定の両方に対応）

    全引数指定例:
      mdx vm deploy -t "Ubuntu 22.04" -n "worker-{a-e}-{0-9}" --pack-type cpu --pack-num 3 --disk 40 --service-level spot -k ~/.ssh/id_ed25519.pub --power-on -y --no-wait
    """
    pid = resolve_project_id(project_id)
    client = get_client()

    selected_tmpl = _resolve_template(client, pid, template)
    segment_uuid = _resolve_segment_for_deploy(client, pid, skip_prompt=yes)
    shared_key = _resolve_ssh_key(key)
    name_pattern = _resolve_name_pattern(name)
    pack_type = _resolve_pack_type(pack_type_opt)
    spec = PACK_SPECS[pack_type]

    if pack_num_opt is not None:
        if not 1 <= pack_num_opt <= spec.max_num:
            fail(f"パック数は 1〜{spec.max_num} の範囲で指定してください")
        pack_num = pack_num_opt
    else:
        pack_num = prompt_int(
            f"パック数 (最大{spec.max_num}):",
            max_val=spec.max_num,
            default=str(spec.default_num),
        )

    if disk is not None:
        disk_size = disk
    else:
        disk_size = prompt_int(
            "ディスクサイズ(GB):", default=str(selected_tmpl.lower_limit_disk)
        )

    service_level = _resolve_service_level(service_level_opt)

    if not power_on and not yes:
        power_on = questionary.confirm("デプロイ後に自動起動しますか？", default=False).unsafe_ask()

    plan = DeployPlan(
        template=selected_tmpl,
        segment_uuid=segment_uuid,
        name_pattern=name_pattern,
        disk_size=disk_size,
        pack_type=pack_type,
        pack_num=pack_num,
        service_level=service_level,
        shared_key=shared_key,
        power_on=power_on,
    )

    _print_deploy_summary(plan)
    if not yes:
        if not questionary.confirm("\nデプロイしますか？").unsafe_ask():
            raise typer.Abort()

    _execute_deploy(client, plan, pid, no_wait=no_wait)


def _resolve_template(client, pid: str, template: str | None):
    """テンプレートを解決する。指定があれば部分一致、なければ一覧から選択。"""
    templates = list_templates(client, pid)
    stop_active_spinner()

    if template:
        matched = [t for t in templates if template.lower() in t.name.lower()]
        if not matched:
            fail(f"テンプレート '{template}' が見つかりません")
        return matched[0]

    if not templates:
        fail("テンプレートがありません")

    def _format(t) -> str:
        os_info = f" [cyan]{t.os_name or ''} {t.os_version or ''}[/cyan]" if t.os_name else ""
        gpu = " [red]GPU必須[/red]" if t.gpu_required else ""
        line = f"{t.name}{os_info}{gpu} [dim]disk≥{t.lower_limit_disk}GB[/dim]"
        if t.description:
            line += f"\n     [dim]{t.description}[/dim]"
        return line

    return select_from_list(templates, _format, title="テンプレート:")


def _resolve_segment_for_deploy(client, pid: str, skip_prompt: bool) -> str:
    """デプロイ先セグメントを解決する。複数あれば選択（-y 時は先頭）。"""
    segments = list_segments(client, pid)
    stop_active_spinner()
    if not segments:
        fail("セグメントがありません")
    if len(segments) == 1 or skip_prompt:
        return segments[0].uuid
    return select_from_list(segments, lambda s: s.name, title="セグメント:").uuid


def _resolve_ssh_key(key: str | None) -> str:
    """SSH公開鍵の内容を解決する。未指定なら ~/.ssh の一覧から選択。"""
    if key:
        key_path = Path(key).expanduser()
    else:
        console.print("\n[bold]SSH公開鍵[/bold]")
        pubkeys = _list_pubkeys()
        if pubkeys:
            console.print("[dim]  ~/.ssh/ にある公開鍵:[/dim]")
            for i, p in enumerate(pubkeys, 1):
                console.print(f"  {i}) {p.name}")
                console.print(f"     [grey50]{_pubkey_preview(p)}[/grey50]")
            console.print("[dim]  番号で選択、または絶対パス/~/... を直接入力[/dim]")
            answer = questionary.text("番号またはパス:", default="1").unsafe_ask()
            if answer.strip().isdigit() and 1 <= int(answer) <= len(pubkeys):
                key_path = pubkeys[int(answer) - 1]
                console.print(f"[green]{key_path.name} が選択されました[/green]")
            else:
                key_path = Path(answer).expanduser()
        else:
            console.print("[yellow]  警告: ~/.ssh/ に .pub ファイルが見つかりません[/yellow]")
            console.print("[dim]  絶対パスまたは ~/... で公開鍵のパスを指定してください[/dim]")
            answer = questionary.text("パス:").unsafe_ask()
            key_path = Path(answer).expanduser()
    if not key_path.is_absolute():
        fail("絶対パスまたは ~/... で指定してください")
    if not key_path.exists():
        fail(f"ファイルが見つかりません: {key_path}")
    return key_path.read_text().strip()


def _resolve_name_pattern(name: str | None) -> str:
    """VM名パターンを解決し、複数台のときは展開結果の概要を表示する。"""
    if name:
        pattern = name
    else:
        console.print("\n[bold]VM名[/bold]")
        console.print("[dim]  パターンで一括作成: my-vm-{0-9} → 10台 (1リクエスト), name-{a-c}-{0-9} → 30台 (3リクエスト)[/dim]")
        pattern = questionary.text("VM名:").unsafe_ask()

    vm_names = expand_name_pattern(pattern)
    deploy_patterns = expand_name_pattern_for_deploy(pattern)
    if len(vm_names) > 1:
        if len(deploy_patterns) < len(vm_names):
            console.print(
                f"  → {len(vm_names)}台 ({len(deploy_patterns)} リクエストにバッチ集約): "
                f"{vm_names[0]} 〜 {vm_names[-1]}"
            )
        else:
            console.print(f"  → {len(vm_names)}台: {vm_names[0]} 〜 {vm_names[-1]}")
    return pattern


def _resolve_pack_type(pack_type_opt: str | None) -> str:
    if pack_type_opt:
        if pack_type_opt not in PACK_SPECS:
            fail(f"不明なパックタイプです: {pack_type_opt}（cpu / gpu）")
        return pack_type_opt
    return questionary.select(
        "パックタイプ:",
        choices=[
            Choice("cpu（1パック = 1コア / 1.51GB RAM）", value="cpu"),
            Choice("gpu（1パック = 18コア / 1GPU / 57.6GB RAM / 40GB VRAM）", value="gpu"),
        ],
    ).unsafe_ask()


def _resolve_service_level(service_level_opt: str | None) -> str:
    if service_level_opt:
        return service_level_opt
    return questionary.select(
        "サービスレベル:",
        choices=[
            Choice("spot（低価格・中断あり）", value="spot"),
            Choice("guarantee（高価格・中断なし）", value="guarantee"),
        ],
    ).unsafe_ask()


def _print_deploy_summary(plan: DeployPlan) -> None:
    vm_names = plan.vm_names
    console.print("\n[bold]デプロイ内容:[/bold]")
    console.print(f"  テンプレート: {plan.template.name}")
    console.print(f"  ディスク:     {plan.disk_size}GB / {plan.pack_type} x {plan.pack_num} / {plan.service_level}")
    console.print(f"  自動起動:     {'あり' if plan.power_on else 'なし'}")
    if len(vm_names) == 1:
        console.print(f"  VM名:         {vm_names[0]}")
    else:
        console.print(f"  VM数:         {len(vm_names)}台 ({vm_names[0]} 〜 {vm_names[-1]})")


def _execute_deploy(client, plan: DeployPlan, pid: str, no_wait: bool) -> None:
    """デプロイ実行（直列、API範囲記法でリクエスト集約）。"""
    requests = plan.to_requests(pid)
    task_ids: list[str] = []
    for i, req in enumerate(requests, 1):
        resp = deploy_vm(client, req)
        task_ids.extend(resp.task_id)
        stop_active_spinner()
        if len(resp.task_id) > 1:
            console.print(
                f"  [green]✓[/green] ({i}/{len(requests)}) {req.vm_name} → {len(resp.task_id)}台分のタスクID"
            )
        else:
            console.print(
                f"  [green]✓[/green] ({i}/{len(requests)}) {req.vm_name} → タスク: {resp.task_id[0]}"
            )

    console.print(f"\n{len(task_ids)}台のデプロイを開始しました")

    if not no_wait and task_ids:
        _print_task_results(_parallel_task_wait(task_ids))


def _resolve_vms(client, pattern: str, project_id: str | None) -> list:
    """パターンからVMリストを解決する。

    UUIDならそのまま、名前パターンならVM一覧から検索。
    """
    if is_uuid(pattern):
        vm = get_vm(client, pattern)
        stop_active_spinner()
        return [vm]

    # パターンマッチ
    pid = resolve_project_id(project_id)
    all_vms = list_vms(client, pid)
    stop_active_spinner()
    all_names = [v.name for v in all_vms]
    matched_names = match_names(pattern, all_names)

    if not matched_names:
        fail(f"パターン '{pattern}' に一致するVMがありません")

    return [v for v in all_vms if v.name in set(matched_names)]


_CHUNK_SIZE = 30


def _fetch_vm_details(client, vms_brief: list) -> list:
    """VMリストの詳細を並列取得する（進捗表示付き）。

    単一の場合は渡されたクライアントで同期取得。
    複数の場合は parallel_get で並列化し、完了ごとにVM名を進捗表示する。
    """
    from mdx_cli.api.parallel import parallel_get
    from mdx_cli.models.vm import VM

    if len(vms_brief) == 1:
        return [get_vm(client, vms_brief[0].uuid)]

    token, base_url = get_auth_context()
    paths = [f"/api/vm/{v.uuid}/" for v in vms_brief]
    with progress_status("詳細取得中", len(vms_brief)) as progress:
        results = parallel_get(
            base_url, token, paths,
            on_progress=lambda idx: progress.advance(vms_brief[idx].name),
            return_exceptions=True,
        )

    vms_detail = []
    missing = []
    for brief, data in zip(vms_brief, results):
        if isinstance(data, Exception):
            missing.append(brief)
            continue
        if "uuid" not in data:
            data["uuid"] = brief.uuid
        vms_detail.append(VM.model_validate(data))

    if missing:
        console.print(
            f"[yellow]※ {len(missing)}台の詳細取得に失敗しました（リトライ後も失敗・サーバー負荷の可能性）:[/yellow]"
        )
        for v in missing:
            console.print(f"  - {v.name} [dim]({v.uuid})[/dim]")

    return vms_detail


def _wait_for_poweroff(running_vms: list, poll_interval: int = 5, max_polls: int = 60) -> list:
    """指定VMが全て PowerOFF になるまで並列ポーリングする（進捗表示付き）。

    戻り値: タイムアウト（poll_interval × max_polls）までに停止を
    確認できなかったVMのリスト。空なら全台停止。
    """
    import asyncio

    token, base_url = get_auth_context()
    settings = get_settings()
    resolved = base_url if base_url.endswith("/") else base_url + "/"

    with progress_status("停止待機中", len(running_vms)) as progress:
        async def _run():
            async with httpx.AsyncClient(
                base_url=resolved,
                timeout=settings.request_timeout,
                headers={"Authorization": f"JWT {token}"},
            ) as ac:
                async def _poll(vm):
                    for _ in range(max_polls):
                        resp = await ac.get(f"/api/vm/{vm.uuid}/")
                        if resp.json().get("status") != "PowerON":
                            progress.advance(f"完了: {vm.name}")
                            return None
                        await asyncio.sleep(poll_interval)
                    return vm
                return await asyncio.gather(*[_poll(v) for v in running_vms])

        results = asyncio.run(_run())

    return [v for v in results if v is not None]


def _ensure_stopped(running_vms: list) -> None:
    """VMの停止完了を待ち、確認できなかったVMがあれば警告して続行確認する。

    稼働中VMへの destroy / reconfigure はAPI側で失敗するため、
    黙って先へ進まず default=False で確認を挟む。
    """
    still_running = _wait_for_poweroff(running_vms)
    if not still_running:
        console.print("  → 停止完了")
        return

    console.print(
        f"\n[yellow]⚠ {len(still_running)}台の停止をタイムアウトまでに確認できませんでした:[/yellow]"
    )
    for v in still_running:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim]")
    if not questionary.confirm(
        "このまま続行しますか？（稼働中のVMは操作に失敗する可能性があります）",
        default=False,
    ).unsafe_ask():
        raise typer.Abort()


def _check_reconfigure_homogeneity(vms: list) -> None:
    """bulk reconfigure で全VMのpack_typeとディスク本数が一致するか検証する。

    不一致の場合はエラー表示してtyper.Exitを送出する。
    """
    pack_types = {v.pack_type for v in vms}
    disk_counts = {len(v.hard_disks) for v in vms}

    if len(pack_types) > 1:
        fail(f"pack_type が混在しているため一括構成変更できません: {pack_types}")
    if len(disk_counts) > 1:
        fail(f"ディスク本数が混在しているため一括構成変更できません: {disk_counts}")


def _parallel_vm_action(vms: list, action_path_fn, action_name: str, json_fn=None) -> list[dict]:
    """VM一括操作を並列実行する。

    action_path_fn: VM → APIパス (例: lambda v: f"/api/vm/{v.uuid}/power_on/")
    json_fn: VM → POSTボディ (省略時は None)

    30台ごとにトークンを事前リフレッシュしてから並列POSTする。
    長時間のバルク操作でもトークンが途中で切れない。
    """
    all_results: list[dict] = []
    with progress_status(action_name, len(vms)) as progress:
        for chunk_start in range(0, len(vms), _CHUNK_SIZE):
            chunk = vms[chunk_start:chunk_start + _CHUNK_SIZE]
            refresh_token_proactive()
            token, base_url = get_auth_context()
            reqs = [{"path": action_path_fn(v), "json": json_fn(v) if json_fn else None} for v in chunk]
            results = parallel_post(
                base_url, token, reqs,
                on_progress=lambda idx, _chunk=chunk: progress.advance(_chunk[idx].name),
            )
            all_results.extend(results)
    return all_results


def _print_task_results(task_results: list[dict]) -> None:
    """タスク完了結果を Completed=緑 / それ以外=赤 で一覧表示する。"""
    for data in task_results:
        name = data.get("object_name", "?")
        status = data.get("status", "?")
        style = "[green]" if status == "Completed" else "[red]"
        console.print(f"  {style}{name}: {status}[/]")


def _parallel_task_wait(task_ids: list[str]) -> list[dict]:
    """複数タスクを並列ポーリングで待機する。"""
    token, base_url = get_auth_context()
    settings = get_settings()

    def on_done(tid: str, data: dict, progress) -> None:
        name = data.get("object_name", tid[:8])
        status = data.get("status", "?")
        progress.advance(f"{name}: {status}")

    with progress_status("タスク完了待ち", len(task_ids)) as progress:
        results = parallel_wait(
            base_url, token, task_ids,
            poll_interval=settings.task_poll_interval,
            timeout=settings.task_poll_timeout,
            on_done=lambda tid, data: on_done(tid, data, progress),
        )
    return results


_TARGET_HELP = "VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"


def _bulk_power_action(
    target: str,
    project_id: str | None,
    *,
    action: str,
    header_verb: str,
    progress_label: str,
    final_verb: str,
    note: str = "",
    danger: bool = False,
    body_fn=None,
) -> None:
    """電源系コマンド共通フロー: 対象解決 → 一覧表示 → 確認 → 並列実行。

    danger=True は対象が1台でも default=False で確認する（reset 等）。
    それ以外は複数台のときのみ確認する。
    """
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    style = "bold red" if danger else "bold"
    console.print(f"\n[{style}]{len(vms)}台を{header_verb}します{note}:[/{style}]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if danger:
        if not questionary.confirm(
            f"\n本当に{len(vms)}台を{header_verb}しますか？", default=False
        ).unsafe_ask():
            raise typer.Abort()
    elif len(vms) > 1:
        if not questionary.confirm(f"\n{len(vms)}台を{header_verb}しますか？").unsafe_ask():
            raise typer.Abort()

    _parallel_vm_action(
        vms, lambda v: vm_action_path(v.uuid, action), progress_label, json_fn=body_fn
    )
    for v in vms:
        console.print(f"  [green]✓[/green] {v.name}")
    console.print(f"\n{len(vms)}台の{final_verb}を実行しました")


@app.command()
def start(
    target: str = typer.Argument(help=_TARGET_HELP),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    service_level: str = typer.Option("spot", "--service-level", "-s", help="サービスレベル"),
) -> None:
    """VM起動（パターンで複数台対応）"""
    _bulk_power_action(
        target, project_id,
        action="power_on",
        header_verb="起動",
        progress_label="起動中",
        final_verb="起動",
        note=f"（{service_level}）",
        body_fn=lambda v: {"service_level": service_level},
    )


@app.command()
def stop(
    target: str = typer.Argument(help=_TARGET_HELP),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM強制停止（パターンで複数台対応）。正常停止は shutdown を使用"""
    _bulk_power_action(
        target, project_id,
        action="power_off",
        header_verb="停止",
        progress_label="強制停止中",
        final_verb="強制停止",
    )


@app.command()
def shutdown(
    target: str = typer.Argument(help=_TARGET_HELP),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM正常シャットダウン（パターンで複数台対応）"""
    _bulk_power_action(
        target, project_id,
        action="shutdown",
        header_verb="シャットダウン",
        progress_label="シャットダウン中",
        final_verb="シャットダウン",
    )


@app.command()
def reboot(
    target: str = typer.Argument(help=_TARGET_HELP),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM再起動（パターンで複数台対応）"""
    _bulk_power_action(
        target, project_id,
        action="reboot",
        header_verb="再起動",
        progress_label="再起動中",
        final_verb="再起動",
    )


@app.command()
def reset(
    target: str = typer.Argument(help=_TARGET_HELP),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VMリセット（パターンで複数台対応）"""
    _bulk_power_action(
        target, project_id,
        action="reset",
        header_verb="リセット",
        progress_label="リセット中",
        final_verb="リセット",
        danger=True,
    )


@app.command()
def reconfigure(
    target: str = typer.Argument(None, help="VM名またはUUID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    no_wait: bool = typer.Option(False, "--no-wait", help="タスク完了を待たない"),
) -> None:
    """VM構成変更（対話式。パック数・ディスクサイズを変更。パターンで複数台対応）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    # VM選択
    if not target:
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        if not all_vms:
            fail("VMがありません")
        selected = select_from_list(
            all_vms, lambda v: f"{v.name} [{v.status}]", title="VM一覧:"
        )
        vms_brief = [selected]
    else:
        vms_brief = _resolve_vms(client, target, project_id)

    # 全VMの詳細を取得
    vms_detail = _fetch_vm_details(client, vms_brief)
    stop_active_spinner()

    if not vms_detail:
        fail("構成変更可能なVMがありません（詳細取得が全て失敗しました）")

    # 複数台なら均質性チェック
    if len(vms_detail) > 1:
        _check_reconfigure_homogeneity(vms_detail)

    # 代表VMの現在構成を表示
    ref = vms_detail[0]
    ref_extra = getattr(ref, "model_extra", {}) or {}

    if len(vms_detail) > 1:
        console.print(f"\n[bold]対象VM ({len(vms_detail)}台):[/bold]")
        for v in vms_detail:
            console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")
        console.print(f"\n[bold]現在の構成（{ref.name} を代表として表示）:[/bold]")
    else:
        console.print(f"\n[bold]{ref.name}[/bold] の現在の構成:")

    console.print(f"  状態:     {ref.status}")
    console.print(f"  パック:   {ref.pack_type or 'cpu'} x {ref.pack_num if ref.pack_num is not None else '?'}")
    console.print(f"  CPU:      {ref_extra.get('cpu', '?')}")
    console.print(f"  メモリ:   {ref_extra.get('memory', '?')}")
    ref_disks = ref.hard_disks
    for d in ref_disks:
        console.print(f"  ディスク: #{d.get('disk_number', '?')}: {d.get('capacity', '?')}")

    # 稼働中VMの停止
    running_vms = [v for v in vms_detail if v.status == "PowerON"]
    if running_vms:
        console.print(
            f"\n[yellow]構成変更にはVMの停止が必要です（稼働中: {len(running_vms)}台）。[/yellow]"
        )
        if not questionary.confirm("停止して構成変更しますか？").unsafe_ask():
            raise typer.Abort()
        _parallel_vm_action(
            running_vms, lambda v: vm_action_path(v.uuid, "shutdown"), "シャットダウン中"
        )
        _ensure_stopped(running_vms)

    # 新しい構成を入力
    console.print("\n[bold]新しい構成（Enterで変更なし）:[/bold]")

    pack_type = ref.pack_type or "cpu"
    current_pack_num = ref.pack_num if ref.pack_num is not None else 3
    spec = PACK_SPECS.get(pack_type, PACK_SPECS["cpu"])

    new_pack_num = prompt_int(
        f"パック数 ({pack_type}, 最大{spec.max_num}):",
        max_val=spec.max_num,
        default=str(current_pack_num),
    )

    console.print(f"  → [cyan]{spec.resource_summary(new_pack_num)}[/cyan]")

    # ディスク新容量（代表VMの各ディスク分を聞き、全VMに同一適用）
    new_capacities: list[int] = []
    for d in ref_disks:
        current_cap = d.get("capacity", "").replace(" GB", "").strip()
        try:
            current_cap_int = int(float(current_cap))
        except (ValueError, TypeError):
            current_cap_int = 40
        new_cap = prompt_int(
            f"ディスク #{d.get('disk_number', '?')} (GB):",
            default=str(current_cap_int),
        )
        new_capacities.append(new_cap)

    # 確認
    console.print("\n[bold]変更内容:[/bold]")
    console.print(
        f"  パック: {pack_type} x {current_pack_num} → {new_pack_num}"
    )
    for d_old, new_cap in zip(ref_disks, new_capacities):
        old_cap = d_old.get("capacity", "?")
        console.print(
            f"  ディスク #{d_old.get('disk_number', '?')}: {old_cap} → {new_cap} GB"
        )
    if len(vms_detail) > 1:
        console.print(f"  対象:   {len(vms_detail)}台")

    if not questionary.confirm("\n構成変更を実行しますか？").unsafe_ask():
        raise typer.Abort()

    # VMごとに個別の config を構築（device_key と segment は各VMの現状を保持）
    segments = list_segments(client, pid)
    stop_active_spinner()
    default_seg = segments[0].uuid if segments else ""
    seg_name_to_uuid = {s.name: s.uuid for s in segments}

    def _build_config(vm) -> dict:
        new_disks = []
        for d, new_cap in zip(vm.hard_disks, new_capacities):
            new_disks.append({
                "disk_number": d.get("disk_number", 1),
                "device_key": d.get("device_key", 2000),
                "capacity": new_cap,
            })
        network_adapters = []
        for n in vm.service_networks:
            network_adapters.append({
                "adapter_number": n.get("adapter_number", 1),
                "segment": seg_name_to_uuid.get(n.get("segment", ""), default_seg),
            })
        if not network_adapters:
            network_adapters = [{"adapter_number": 1, "segment": default_seg}]
        return {
            "hard_disks": new_disks,
            "network_adapters": network_adapters,
            "pack_num": new_pack_num,
        }

    # 単一台 or 複数台で分岐
    if len(vms_detail) == 1:
        task_id = reconfigure_vm(client, vms_detail[0].uuid, _build_config(vms_detail[0]))
        stop_active_spinner()
        console.print(f"構成変更タスク開始: {task_id}")
        task_ids = [task_id]
    else:
        results = _parallel_vm_action(
            vms_detail,
            lambda v: vm_action_path(v.uuid, "reconfigure"),
            "構成変更中",
            json_fn=_build_config,
        )
        task_ids = []
        for v, r in zip(vms_detail, results):
            if isinstance(r, Exception):
                console.print(f"  [red]✗[/red] {v.name} → {r}")
                continue
            tid = r.get("task_id", "") if isinstance(r, dict) else ""
            if isinstance(tid, list):
                tid = tid[0] if tid else ""
            if tid:
                task_ids.append(tid)
                console.print(f"  [green]✓[/green] {v.name} → タスク: {tid}")
        console.print(f"\n{len(task_ids)}台の構成変更を開始しました")

    if not no_wait and task_ids:
        _print_task_results(_parallel_task_wait(task_ids))


@app.command()
def destroy(
    target: str = typer.Argument(help="VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    no_wait: bool = typer.Option(False, "--no-wait", help="タスク完了を待たない"),
) -> None:
    """VM削除（パターンで複数台対応）"""
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    # PowerON の VM があれば先に停止
    running_vms = [v for v in vms if v.status == "PowerON"]
    if running_vms:
        console.print(f"\n[yellow]{len(running_vms)}台が稼働中です。先に停止します。[/yellow]")
        for v in running_vms:
            console.print(f"  {v.name} [{v.status}]")

    console.print(f"\n[bold red]{len(vms)}台を削除します:[/bold red]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if not questionary.confirm(f"\n本当に{len(vms)}台を削除しますか？", default=False).unsafe_ask():
        raise typer.Abort()

    # 稼働中VMを並列停止して完了を待つ
    if running_vms:
        _parallel_vm_action(running_vms, lambda v: vm_action_path(v.uuid, "power_off"), "停止中")
        console.print(f"  {len(running_vms)}台の停止リクエスト送信完了")
        _ensure_stopped(running_vms)
        console.print("")

    # 並列削除
    destroy_results = _parallel_vm_action(vms, lambda v: vm_action_path(v.uuid, "destroy"), "削除中")

    task_ids: list[str] = []
    for v, resp_data in zip(vms, destroy_results):
        tid = resp_data.get("task_id", "")
        if isinstance(tid, list):
            tid = tid[0] if tid else ""
        task_ids.append(tid)
        console.print(f"  [green]✓[/green] {v.name} → タスク: {tid}")

    console.print(f"\n{len(task_ids)}台の削除を開始しました")

    if not no_wait:
        _print_task_results(_parallel_task_wait(task_ids))


@app.command()
def sync(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM情報同期"""
    pid = resolve_project_id(project_id)
    client = get_client()
    sync_vms(client, pid)
    stop_active_spinner()
    console.print("VM情報を同期しました")


@app.command()
def ssh(
    target: str = typer.Argument(None, help="VM名またはUUID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    user: str = typer.Option("mdxuser", "--user", "-u", help="SSHユーザー名"),
    identity: str = typer.Option(None, "--identity", "-i", help="秘密鍵のパス（~/ 対応）"),
    use_global_ip: bool = typer.Option(False, "--global", "-g", help="グローバルIPを使用"),
) -> None:
    """VMにSSH接続する"""
    import os

    client = get_client()

    if not target:
        # 一覧から選択
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        running = [v for v in all_vms if v.status == "PowerON"]
        if not running:
            fail("稼働中のVMがありません")
        selected = select_from_list(running, lambda v: v.name, title="稼働中のVM:")
        vm_uuid = selected.uuid
    elif is_uuid(target):
        vm_uuid = target
    else:
        # 名前で検索
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        matched = [v for v in all_vms if v.name == target]
        if not matched:
            fail(f"VM '{target}' が見つかりません")
        vm_uuid = matched[0].uuid

    # VM詳細からIPを取得
    vm = get_vm(client, vm_uuid)
    stop_active_spinner()

    nets = vm.service_networks
    if not nets:
        fail("ネットワーク情報がありません")

    net = nets[0]
    global_ip = net.get("global_ip", "")
    ipv4_list = net.get("ipv4_address", [])
    private_ip = ipv4_list[0] if ipv4_list else ""

    if use_global_ip and global_ip:
        host = global_ip
    elif private_ip:
        host = private_ip
    else:
        fail("IPアドレスが見つかりません")

    # ユーザー名を自動検出（テンプレートの login_username）
    if user == "mdxuser":
        host_name = vm.host_name or ""
        if host_name:
            try:
                pid = resolve_project_id(project_id)
                templates = list_templates(client, pid)
                stop_active_spinner()
                for t in templates:
                    if t.template_name and host_name in t.template_name and t.login_username:
                        user = t.login_username
                        break
            except Exception:
                pass

    ssh_cmd = ["ssh"]
    if identity:
        key_path = Path(identity).expanduser()
        ssh_cmd.extend(["-i", str(key_path)])
    ssh_cmd.append(f"{user}@{host}")

    console.print(f"[dim]{' '.join(ssh_cmd)}[/dim]")
    os.execvp("ssh", ssh_cmd)


# CSV用のヘッダー（Webポータルと同じ列構成）
_CSV_HEADER = ["VM_NAME"]
for _i in range(1, 9):
    _CSV_HEADER.extend([f"SERVICE_NET_{_i}_IPv4", f"SERVICE_NET_{_i}_IPv6"])
for _i in range(1, 9):
    _CSV_HEADER.extend([f"STORAGE_NET_{_i}_IPv4", f"STORAGE_NET_{_i}_IPv6"])


def _vm_csv_row(data: dict) -> list[str]:
    """APIレスポンスからCSV1行分のリストを生成する。"""
    row = [data.get("name", "")]
    for nets_key, prefix in [("service_networks", "SERVICE_NET"), ("storage_networks", "STORAGE_NET")]:
        nets = {n.get("adapter_number"): n for n in data.get(nets_key, [])}
        for i in range(1, 9):
            net = nets.get(i, {})
            ipv4 = ",".join(net.get("ipv4_address", []))
            ipv6 = ",".join(net.get("ipv6_address", []))
            row.extend([ipv4, ipv6])
    return row


@app.command()
def csv(
    target: str = typer.Argument(None, help="VM名パターン（省略時は全VM）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    output: str = typer.Option(None, "--output", "-o", help="出力ファイルパス（省略時は stdout）"),
) -> None:
    """VM情報をCSVでダウンロード（Webポータルと同じ形式）"""
    import csv as csv_mod
    import io

    pid = resolve_project_id(project_id)
    client = get_client()
    all_vms = list_vms(client, pid)
    stop_active_spinner()

    if target:
        vm_names = [v.name for v in all_vms]
        matched_names = set(match_names(target, vm_names))
        vms = [v for v in all_vms if v.name in matched_names]
        if not vms:
            fail(f"パターン '{target}' に一致するVMがありません")
    else:
        vms = all_vms

    from mdx_cli.api.parallel import parallel_get

    token, base_url = get_auth_context()
    paths = [f"/api/vm/{v.uuid}/csv/" for v in vms]
    with progress_status("CSV取得中", len(vms)) as progress:
        results = parallel_get(
            base_url, token, paths, max_concurrent=50,
            on_progress=lambda idx: progress.advance(),
        )

    rows = [_vm_csv_row(data) for data in results]

    # CSV生成
    buf = io.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(_CSV_HEADER)
    writer.writerows(rows)
    csv_text = buf.getvalue()

    if output:
        out_path = Path(output).expanduser()
        out_path.write_text(csv_text)
        console.print(f"[green]{len(vms)}台のVM情報を {out_path} に保存しました[/green]")
    else:
        print(csv_text, end="")
