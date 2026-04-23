from pathlib import Path

import httpx
import questionary
from questionary import Choice
import typer
from rich.console import Console

from mdx_cli.api.endpoints.networks import list_segments
from mdx_cli.api.endpoints.tasks import wait_for_task
from mdx_cli.api.endpoints.templates import list_templates
from mdx_cli.api.endpoints.vms import (
    deploy_vm,
    destroy_vm,
    get_vm,
    get_vm_csv,
    list_vms,
    power_off_vm,
    power_on_vm,
    reboot_vm,
    reconfigure_vm,
    reset_vm,
    shutdown_vm,
    sync_vms,
)
from mdx_cli.api.parallel import parallel_post, parallel_wait
from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands._common import get_client, ask_or_abort, resolve_project_id
from mdx_cli.credentials.store import CredentialStore
from mdx_cli.commands._name_pattern import (
    expand_name_pattern,
    expand_name_pattern_for_deploy,
    match_names,
)
from mdx_cli.models.vm import VMDeployRequest
from mdx_cli.output.formatting import render
from mdx_cli.output.tables import VM_COLUMNS
from mdx_cli.settings import Settings

app = typer.Typer(no_args_is_help=True, help="仮想マシン管理")
console = Console()



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
    if target and len(target) == 36 and "-" in target:
        vm = get_vm(client, target)
    elif target:
        # 名前で検索
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        matched = [v for v in all_vms if v.name == target]
        if not matched:
            console.print(f"[red]VM '{target}' が見つかりません[/red]")
            raise typer.Exit(code=1)
        vm = get_vm(client, matched[0].uuid)
    else:
        # 一覧から選択
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        console.print("\n[bold]VM一覧:[/bold]")
        for i, v in enumerate(all_vms, 1):
            console.print(f"  {i}) {v.name} [{v.status}]")
        idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
        vm = get_vm(client, all_vms[idx].uuid)

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
    console.print(f"  パック:         {extra.get('pack_type', '-')} x {extra.get('pack_num', '-')}")
    console.print(f"  NVLink:         {extra.get('nvlink', '-')}")

    # ディスク
    disks = extra.get("hard_disks", [])
    if disks:
        console.print(f"\n[bold]ディスク:[/bold]")
        for d in disks:
            console.print(f"  #{d.get('disk_number', '?')}: {d.get('capacity', '?')} ({d.get('datastore', '')})")

    # ネットワーク
    nets = extra.get("service_networks", [])
    if nets:
        console.print(f"\n[bold]ネットワーク:[/bold]")
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
    snets = extra.get("storage_networks", [])
    if snets:
        console.print(f"\n[bold]ストレージネットワーク:[/bold]")
        for sn in snets:
            ipv4 = ", ".join(sn.get("ipv4_address", []))
            console.print(f"  アダプタ {sn.get('adapter_number', '?')}: {ipv4} ({sn.get('storage_network_type', '')})")

    # VMware Tools
    tools = extra.get("vmware_tools", {})
    if tools:
        console.print(f"\n[bold]VMware Tools:[/bold]")
        console.print(f"  状態:     {tools.get('status', '-')}")
        console.print(f"  バージョン: {tools.get('version', '-')}")

    console.print()


def _find_default_pubkey_path() -> str | None:
    """~/.ssh から公開鍵パスを探す。"""
    ssh_dir = Path.home() / ".ssh"
    # 標準的な鍵名を優先
    for name in ["id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"]:
        path = ssh_dir / name
        if path.exists():
            return f"~/.ssh/{name}"
    # なければ *.pub を探す
    pubs = sorted(ssh_dir.glob("*.pub"))
    if pubs:
        return f"~/.ssh/{pubs[0].name}"
    return None


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

    # --- テンプレート ---
    templates = list_templates(client, pid)
    stop_active_spinner()

    if template:
        matched = [t for t in templates if template.lower() in t.name.lower()]
        if not matched:
            console.print(f"[red]テンプレート '{template}' が見つかりません[/red]")
            raise typer.Exit(code=1)
        selected_tmpl = matched[0]
    else:
        console.print("\n[bold]テンプレート:[/bold]")
        for i, t in enumerate(templates, 1):
            os_info = f" [cyan]{t.os_name or ''} {t.os_version or ''}[/cyan]" if t.os_name else ""
            gpu = " [red]GPU必須[/red]" if t.gpu_required else ""
            disk_info = f" [dim]disk≥{t.lower_limit_disk}GB[/dim]"
            console.print(f"  {i}) {t.name}{os_info}{gpu}{disk_info}")
            if t.description:
                console.print(f"     [dim]{t.description}[/dim]")
        tmpl_idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
        selected_tmpl = templates[tmpl_idx]

    # --- セグメント ---
    segments = list_segments(client, pid)
    stop_active_spinner()
    selected_seg = segments[0]
    if len(segments) > 1 and not yes:
        console.print("\n[bold]セグメント:[/bold]")
        for i, s in enumerate(segments, 1):
            console.print(f"  {i}) {s.name}")
        seg_idx = int(questionary.text("番号を入力:").unsafe_ask()) - 1
        selected_seg = segments[seg_idx]

    # --- SSH公開鍵 ---
    if key:
        key_path = Path(key).expanduser()
    else:
        default_path = _find_default_pubkey_path() or ""
        console.print("\n[bold]SSH公開鍵[/bold]")
        console.print("[dim]  絶対パスまたは ~/... で指定。デフォルトは ~/.ssh/ から自動検出[/dim]")
        key_path_input = questionary.text("パス:", default=default_path).unsafe_ask()
        key_path = Path(key_path_input).expanduser()
    if not key_path.is_absolute():
        console.print("[red]絶対パスまたは ~/... で指定してください[/red]")
        raise typer.Exit(code=1)
    if not key_path.exists():
        console.print(f"[red]ファイルが見つかりません: {key_path}[/red]")
        raise typer.Exit(code=1)
    shared_key = key_path.read_text().strip()

    # --- VM名 ---
    if name:
        vm_name_pattern = name
    else:
        console.print("\n[bold]VM名[/bold]")
        console.print("[dim]  パターンで一括作成: my-vm-{0-9} → 10台 (1リクエスト), name-{a-c}-{0-9} → 30台 (3リクエスト)[/dim]")
        vm_name_pattern = questionary.text("VM名:").unsafe_ask()
    vm_names = expand_name_pattern(vm_name_pattern)
    deploy_patterns = expand_name_pattern_for_deploy(vm_name_pattern)
    if len(vm_names) > 1:
        if len(deploy_patterns) < len(vm_names):
            console.print(
                f"  → {len(vm_names)}台 ({len(deploy_patterns)} リクエストにバッチ集約): "
                f"{vm_names[0]} 〜 {vm_names[-1]}"
            )
        else:
            console.print(f"  → {len(vm_names)}台: {vm_names[0]} 〜 {vm_names[-1]}")

    # --- パックタイプ ---
    if pack_type_opt:
        pack_type = pack_type_opt
    else:
        pack_type = questionary.select(
            "パックタイプ:",
            choices=[
                Choice("cpu（1パック = 1コア / 1.51GB RAM）", value="cpu"),
                Choice("gpu（1パック = 18コア / 1GPU / 57.6GB RAM / 40GB VRAM）", value="gpu"),
            ],
        ).unsafe_ask()

    max_pack = 152 if pack_type == "cpu" else 8
    mem_per_pack = 1.51 if pack_type == "cpu" else 57.60

    # --- パック数 ---
    if pack_num_opt is not None:
        pack_num = pack_num_opt
    else:
        default_pack = "3" if pack_type == "cpu" else "1"
        pack_num = int(questionary.text(f"パック数 (最大{max_pack}):", default=default_pack).unsafe_ask())

    # --- ディスク ---
    if disk is not None:
        disk_size = disk
    else:
        disk_size = int(questionary.text("ディスクサイズ(GB):", default=str(selected_tmpl.lower_limit_disk)).unsafe_ask())

    # --- サービスレベル ---
    if service_level_opt:
        service_level = service_level_opt
    else:
        service_level = questionary.select(
            "サービスレベル:",
            choices=[
                Choice("spot（低価格・中断あり）", value="spot"),
                Choice("guarantee（高価格・中断なし）", value="guarantee"),
            ],
        ).unsafe_ask()

    # --- 自動起動 ---
    if not power_on and not yes:
        power_on = questionary.confirm("デプロイ後に自動起動しますか？", default=False).unsafe_ask()

    # --- 確認 ---
    total_mem = pack_num * mem_per_pack
    console.print(f"\n[bold]デプロイ内容:[/bold]")
    console.print(f"  テンプレート: {selected_tmpl.name}")
    console.print(f"  ディスク:     {disk_size}GB / {pack_type} x {pack_num} / {service_level}")
    console.print(f"  自動起動:     {'あり' if power_on else 'なし'}")
    if len(vm_names) == 1:
        console.print(f"  VM名:         {vm_names[0]}")
    else:
        console.print(f"  VM数:         {len(vm_names)}台 ({vm_names[0]} 〜 {vm_names[-1]})")

    if not yes:
        if not questionary.confirm("\nデプロイしますか？").unsafe_ask():
            raise typer.Abort()

    # --- デプロイ実行（直列、API範囲記法でリクエスト集約） ---
    task_ids: list[str] = []
    for i, pattern in enumerate(deploy_patterns, 1):
        req = VMDeployRequest(
            catalog=selected_tmpl.uuid,
            project=pid,
            vm_name=pattern,
            disk_size=disk_size,
            pack_type=pack_type,
            pack_num=pack_num,
            service_level=service_level,
            network_adapters=[{"adapter_number": 1, "segment": selected_seg.uuid}],
            shared_key=shared_key,
            template_name=selected_tmpl.template_name or selected_tmpl.name,
            os_type=selected_tmpl.os_type or "Linux",
            power_on=power_on,
        )
        resp = deploy_vm(client, req)
        task_ids.extend(resp.task_id)
        stop_active_spinner()
        if len(resp.task_id) > 1:
            console.print(
                f"  [green]✓[/green] ({i}/{len(deploy_patterns)}) {pattern} → {len(resp.task_id)}台分のタスクID"
            )
        else:
            console.print(
                f"  [green]✓[/green] ({i}/{len(deploy_patterns)}) {pattern} → タスク: {resp.task_id[0]}"
            )

    console.print(f"\n{len(task_ids)}台のデプロイを開始しました")

    if not no_wait and task_ids:
        task_results = _parallel_task_wait(task_ids)
        for data in task_results:
            obj_name = data.get("object_name", "?")
            status = data.get("status", "?")
            style = "[green]" if status == "Completed" else "[red]"
            console.print(f"  {style}{obj_name}: {status}[/]")


def _resolve_vms(client, pattern: str, project_id: str | None) -> list:
    """パターンからVMリストを解決する。

    UUIDならそのまま、名前パターンならVM一覧から検索。
    """
    # UUIDっぽければ直接返す
    if len(pattern) == 36 and "-" in pattern:
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
        console.print(f"[red]パターン '{pattern}' に一致するVMがありません[/red]")
        raise typer.Exit(code=1)

    return [v for v in all_vms if v.name in set(matched_names)]


def _get_token_and_base() -> tuple[str, str]:
    """並列API用にトークンとベースURLを取得する。"""
    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    return store.load_token() or "", settings.base_url


def _refresh_token_proactive() -> None:
    """バルク操作前にトークンを事前リフレッシュして保存する。

    parallel_post は MDXAuth を経由しないため、途中で401を食らうと
    リトライで無駄なリクエストが発生する。事前に1回refreshしておくことで、
    並列リクエスト全体を新鮮なトークンで送れる。
    失敗しても例外は投げず、既存トークンで続行（MDXAuth の 401 ハンドリングが保険）。
    """
    import logging
    logger = logging.getLogger("mdx_cli")

    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    token = store.load_token()
    if not token:
        return

    try:
        with httpx.Client(
            base_url=settings.base_url,
            timeout=30,
            transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        ) as client:
            resp = client.post("/api/refresh/", json={"token": token})
            if resp.status_code == 200:
                new_token = resp.json().get("token")
                if new_token:
                    store.save_token(new_token)
                    logger.debug("バルク操作前にトークンをリフレッシュしました")
    except Exception as e:
        logger.debug("事前リフレッシュに失敗（既存トークンで続行）: %s", e)


_CHUNK_SIZE = 30


def _parallel_vm_action(vms: list, action_path_fn, action_name: str, json_fn=None) -> list[dict]:
    """VM一括操作を並列実行する。

    action_path_fn: VM → APIパス (例: lambda v: f"/api/vm/{v.uuid}/power_on/")
    json_fn: VM → POSTボディ (省略時は None)

    30台ごとにトークンを事前リフレッシュしてから並列POSTする。
    長時間のバルク操作でもトークンが途中で切れない。
    """
    from mdx_cli.api.spinner import _console as spin_console
    from rich.status import Status

    status_display = Status("", console=spin_console, spinner="dots")
    status_display.start()
    done_count = 0
    total = len(vms)

    def on_progress(idx: int) -> None:
        nonlocal done_count
        done_count += 1
        status_display.update(f"{action_name}... ({done_count}/{total})")

    all_results: list[dict] = []
    for chunk_start in range(0, total, _CHUNK_SIZE):
        chunk = vms[chunk_start:chunk_start + _CHUNK_SIZE]
        _refresh_token_proactive()
        token, base_url = _get_token_and_base()
        reqs = [{"path": action_path_fn(v), "json": json_fn(v) if json_fn else None} for v in chunk]
        results = parallel_post(base_url, token, reqs, on_progress=on_progress)
        all_results.extend(results)

    status_display.stop()
    return all_results


def _parallel_task_wait(task_ids: list[str]) -> list[dict]:
    """複数タスクを並列ポーリングで待機する。"""
    from mdx_cli.api.spinner import _console as spin_console
    from rich.status import Status

    token, base_url = _get_token_and_base()
    settings = Settings()

    status_display = Status("", console=spin_console, spinner="dots")
    status_display.start()
    done_count = 0

    def on_done(tid: str, data: dict) -> None:
        nonlocal done_count
        done_count += 1
        name = data.get("object_name", tid[:8])
        status = data.get("status", "?")
        status_display.update(f"タスク完了待ち... ({done_count}/{len(task_ids)}) {name}: {status}")

    results = parallel_wait(
        base_url, token, task_ids,
        poll_interval=settings.task_poll_interval,
        timeout=settings.task_poll_timeout,
        on_done=on_done,
    )
    status_display.stop()
    return results


@app.command()
def start(
    target: str = typer.Argument(help="VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    service_level: str = typer.Option("spot", "--service-level", "-s", help="サービスレベル"),
) -> None:
    """VM起動（パターンで複数台対応）"""
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    console.print(f"\n[bold]{len(vms)}台を起動します（{service_level}）:[/bold]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if len(vms) > 1:
        if not questionary.confirm(f"\n{len(vms)}台を起動しますか？").unsafe_ask():
            raise typer.Abort()

    _parallel_vm_action(
        vms,
        lambda v: f"/api/vm/{v.uuid}/power_on/",
        "起動中",
        json_fn=lambda v: {"service_level": service_level},
    )
    for v in vms:
        console.print(f"  [green]✓[/green] {v.name}")
    console.print(f"\n{len(vms)}台の起動を実行しました")


@app.command()
def stop(
    target: str = typer.Argument(help="VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM強制停止（パターンで複数台対応）。正常停止は shutdown を使用"""
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    console.print(f"\n[bold]{len(vms)}台を停止します:[/bold]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if len(vms) > 1:
        if not questionary.confirm(f"\n{len(vms)}台を停止しますか？").unsafe_ask():
            raise typer.Abort()

    _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/power_off/", "強制停止中")
    for v in vms:
        console.print(f"  [green]✓[/green] {v.name}")
    console.print(f"\n{len(vms)}台の強制停止を実行しました")


@app.command()
def shutdown(
    target: str = typer.Argument(help="VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM正常シャットダウン（パターンで複数台対応）"""
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    console.print(f"\n[bold]{len(vms)}台をシャットダウンします:[/bold]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if len(vms) > 1:
        if not questionary.confirm(f"\n{len(vms)}台をシャットダウンしますか？").unsafe_ask():
            raise typer.Abort()

    _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/shutdown/", "シャットダウン中")
    for v in vms:
        console.print(f"  [green]✓[/green] {v.name}")
    console.print(f"\n{len(vms)}台のシャットダウンを実行しました")


@app.command()
def reboot(
    target: str = typer.Argument(help="VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VM再起動（パターンで複数台対応）"""
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    console.print(f"\n[bold]{len(vms)}台を再起動します:[/bold]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if len(vms) > 1:
        if not questionary.confirm(f"\n{len(vms)}台を再起動しますか？").unsafe_ask():
            raise typer.Abort()

    _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/reboot/", "再起動中")
    for v in vms:
        console.print(f"  [green]✓[/green] {v.name}")
    console.print(f"\n{len(vms)}台の再起動を実行しました")


@app.command()
def reset(
    target: str = typer.Argument(help="VM ID、名前、またはパターン (例: 'crawler-*' ※シェルでクォート必須)"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
) -> None:
    """VMリセット（パターンで複数台対応）"""
    client = get_client()
    vms = _resolve_vms(client, target, project_id)

    console.print(f"\n[bold red]{len(vms)}台をリセットします:[/bold red]")
    for v in vms:
        console.print(f"  {v.name} [dim]({v.uuid})[/dim] [{v.status}]")

    if not questionary.confirm(f"\n本当に{len(vms)}台をリセットしますか？", default=False).unsafe_ask():
        raise typer.Abort()

    _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/reset/", "リセット中")
    for v in vms:
        console.print(f"  [green]✓[/green] {v.name}")
    console.print(f"\n{len(vms)}台のリセットを実行しました")


@app.command()
def reconfigure(
    target: str = typer.Argument(None, help="VM名またはUUID（省略時は一覧から選択）"),
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID", envvar="MDX_PROJECT_ID"),
    no_wait: bool = typer.Option(False, "--no-wait", help="タスク完了を待たない"),
) -> None:
    """VM構成変更（対話式。パック数・ディスクサイズを変更）"""
    pid = resolve_project_id(project_id)
    client = get_client()

    # VM選択
    if not target:
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        console.print("\n[bold]VM一覧:[/bold]")
        for i, v in enumerate(all_vms, 1):
            console.print(f"  {i}) {v.name} [{v.status}]")
        idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
        selected_vm = all_vms[idx]
    elif len(target) == 36 and "-" in target:
        selected_vm = None
        vm_uuid = target
    else:
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        matched = [v for v in all_vms if v.name == target]
        if not matched:
            console.print(f"[red]VM '{target}' が見つかりません[/red]")
            raise typer.Exit(code=1)
        selected_vm = matched[0]

    if selected_vm:
        vm_uuid = selected_vm.uuid

    # VM詳細を取得
    vm = get_vm(client, vm_uuid)
    stop_active_spinner()
    extra = getattr(vm, "model_extra", {}) or {}

    # 現在の構成を表示
    console.print(f"\n[bold]{vm.name}[/bold] の現在の構成:")
    console.print(f"  状態:     {vm.status}")
    console.print(f"  パック:   {extra.get('pack_type', 'cpu')} x {extra.get('pack_num', '?')}")
    console.print(f"  CPU:      {extra.get('cpu', '?')}")
    console.print(f"  メモリ:   {extra.get('memory', '?')}")
    disks = extra.get("hard_disks", [])
    for d in disks:
        console.print(f"  ディスク: #{d.get('disk_number', '?')}: {d.get('capacity', '?')}")

    # 稼働中なら停止が必要
    if vm.status == "PowerON":
        console.print(f"\n[yellow]構成変更にはVMの停止が必要です。[/yellow]")
        if not questionary.confirm("VMを停止して構成変更しますか？").unsafe_ask():
            raise typer.Abort()
        shutdown_vm(client, vm_uuid)
        stop_active_spinner()
        console.print("シャットダウン中...")
        import time
        for _ in range(60):
            time.sleep(5)
            vm_check = get_vm(client, vm_uuid)
            stop_active_spinner()
            if vm_check.status != "PowerON":
                console.print(f"  状態: {vm_check.status}")
                break

    # 新しい構成を入力
    console.print(f"\n[bold]新しい構成（Enterで変更なし）:[/bold]")

    pack_type = extra.get("pack_type", "cpu")
    current_pack_num = extra.get("pack_num", 3)
    if pack_type == "cpu":
        max_pack = 152
        mem_per_pack = 1.51
    else:
        max_pack = 8
        mem_per_pack = 57.60

    new_pack_num = int(questionary.text(
        f"パック数 ({pack_type}, 最大{max_pack}):",
        default=str(current_pack_num),
    ).unsafe_ask())

    new_total_mem = new_pack_num * mem_per_pack
    if pack_type == "cpu":
        console.print(f"  → [cyan]{new_pack_num}コア / {new_total_mem:.1f}GB RAM[/cyan]")
    else:
        console.print(f"  → [cyan]{new_pack_num * 18}コア / {new_pack_num}GPU / {new_total_mem:.1f}GB RAM[/cyan]")

    # ディスクサイズ変更
    new_disks = []
    for d in disks:
        current_cap = d.get("capacity", "").replace(" GB", "").strip()
        try:
            current_cap_int = int(float(current_cap))
        except (ValueError, TypeError):
            current_cap_int = 40
        new_cap = int(questionary.text(
            f"ディスク #{d.get('disk_number', '?')} (GB):",
            default=str(current_cap_int),
        ).unsafe_ask())
        new_disks.append({
            "disk_number": d.get("disk_number", 1),
            "device_key": d.get("device_key", 2000),
            "capacity": new_cap,
        })

    # ネットワーク（現在の構成をそのまま維持）
    nets = extra.get("service_networks", [])
    network_adapters = []
    segments = list_segments(client, pid)
    stop_active_spinner()
    default_seg = segments[0].uuid if segments else ""
    for n in nets:
        seg_name = n.get("segment", "")
        seg_uuid = default_seg
        for s in segments:
            if s.name == seg_name:
                seg_uuid = s.uuid
                break
        network_adapters.append({
            "adapter_number": n.get("adapter_number", 1),
            "segment": seg_uuid,
        })
    if not network_adapters:
        network_adapters = [{"adapter_number": 1, "segment": default_seg}]

    # 確認
    console.print(f"\n[bold]変更内容:[/bold]")
    console.print(f"  パック: {pack_type} x {current_pack_num} → {new_pack_num}")
    for d_old, d_new in zip(disks, new_disks):
        old_cap = d_old.get("capacity", "?")
        console.print(f"  ディスク #{d_new['disk_number']}: {old_cap} → {d_new['capacity']} GB")

    if not questionary.confirm("\n構成変更を実行しますか？").unsafe_ask():
        raise typer.Abort()

    config = {
        "hard_disks": new_disks,
        "network_adapters": network_adapters,
        "pack_num": new_pack_num,
    }
    task_id = reconfigure_vm(client, vm_uuid, config)
    stop_active_spinner()
    console.print(f"構成変更タスク開始: {task_id}")

    if not no_wait:
        settings = Settings()
        task = wait_for_task(client, task_id, poll_interval=settings.task_poll_interval, timeout=settings.task_poll_timeout)
        stop_active_spinner()
        status_style = "[green]" if task.status.value == "Completed" else "[red]"
        console.print(f"  {status_style}タスク完了: {task.status.value}[/]")


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
        _parallel_vm_action(running_vms, lambda v: f"/api/vm/{v.uuid}/power_off/", "停止中")
        console.print(f"  {len(running_vms)}台の停止リクエスト送信完了")

        # 全VMがPowerOFFになるまで並列ポーリング
        import asyncio
        token, base_url = _get_token_and_base()
        settings = Settings()

        async def _wait_poweroff():
            resolved = base_url if base_url.endswith("/") else base_url + "/"
            async with httpx.AsyncClient(base_url=resolved, timeout=settings.request_timeout, headers={"Authorization": f"JWT {token}"}) as ac:
                async def _poll(vid):
                    for _ in range(60):
                        resp = await ac.get(f"/api/vm/{vid}/")
                        if resp.json().get("status") != "PowerON":
                            return
                        await asyncio.sleep(5)
                await asyncio.gather(*[_poll(v.uuid) for v in running_vms])

        import httpx as httpx_mod
        asyncio.run(_wait_poweroff())
        console.print(f"  → 停止完了")
        console.print("")

    # 並列削除
    destroy_results = _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/destroy/", "削除中")

    task_ids: list[str] = []
    for v, resp_data in zip(vms, destroy_results):
        tid = resp_data.get("task_id", "")
        if isinstance(tid, list):
            tid = tid[0] if tid else ""
        task_ids.append(tid)
        console.print(f"  [green]✓[/green] {v.name} → タスク: {tid}")

    console.print(f"\n{len(task_ids)}台の削除を開始しました")

    if not no_wait:
        task_results = _parallel_task_wait(task_ids)
        for data in task_results:
            name = data.get("object_name", "?")
            status = data.get("status", "?")
            style = "[green]" if status == "Completed" else "[red]"
            console.print(f"  {style}{name}: {status}[/]")


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
    import subprocess

    client = get_client()

    if not target:
        # 一覧から選択
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        running = [v for v in all_vms if v.status == "PowerON"]
        if not running:
            console.print("[red]稼働中のVMがありません[/red]")
            raise typer.Exit(code=1)
        console.print("\n[bold]稼働中のVM:[/bold]")
        for i, v in enumerate(running, 1):
            console.print(f"  {i}) {v.name}")
        idx = int(questionary.text("\n番号を入力:").unsafe_ask()) - 1
        vm_uuid = running[idx].uuid
    elif len(target) == 36 and "-" in target:
        vm_uuid = target
    else:
        # 名前で検索
        pid = resolve_project_id(project_id)
        all_vms = list_vms(client, pid)
        stop_active_spinner()
        matched = [v for v in all_vms if v.name == target]
        if not matched:
            console.print(f"[red]VM '{target}' が見つかりません[/red]")
            raise typer.Exit(code=1)
        vm_uuid = matched[0].uuid

    # VM詳細からIPを取得
    vm = get_vm(client, vm_uuid)
    stop_active_spinner()

    extra = getattr(vm, "model_extra", {}) or {}
    nets = extra.get("service_networks", [])

    if not nets:
        console.print("[red]ネットワーク情報がありません[/red]")
        raise typer.Exit(code=1)

    net = nets[0]
    global_ip = net.get("global_ip", "")
    ipv4_list = net.get("ipv4_address", [])
    private_ip = ipv4_list[0] if ipv4_list else ""

    if use_global_ip and global_ip:
        host = global_ip
    elif private_ip:
        host = private_ip
    else:
        console.print("[red]IPアドレスが見つかりません[/red]")
        raise typer.Exit(code=1)

    # ユーザー名を自動検出（テンプレートの login_username）
    if user == "mdxuser":
        host_name = extra.get("host_name", "")
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
            console.print(f"[red]パターン '{target}' に一致するVMがありません[/red]")
            raise typer.Exit(code=1)
    else:
        vms = all_vms

    from mdx_cli.api.parallel import parallel_get
    from mdx_cli.api.spinner import _console as spin_console
    from rich.status import Status

    status_display = Status("", console=spin_console, spinner="dots")
    status_display.start()
    done_count = 0

    def on_progress(idx: int) -> None:
        nonlocal done_count
        done_count += 1
        status_display.update(f"CSV取得中... ({done_count}/{len(vms)})")

    settings = Settings()
    store = CredentialStore(config_dir=settings.config_dir)
    token = store.load_token() or ""
    paths = [f"/api/vm/{v.uuid}/csv/" for v in vms]
    results = parallel_get(settings.base_url, token, paths, max_concurrent=50, on_progress=on_progress)
    status_display.stop()

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
