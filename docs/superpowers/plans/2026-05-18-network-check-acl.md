# network check-acl と check-ip --fix 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 死んだVM宛のACL/DNAT（再利用されると危険な「穴」）を検出する `mdx network check-acl` を新設し、`check-ip` に `--fix` を追加する。

**Architecture:** すべて `src/mdx_cli/commands/network.py` に実装。`check-ip` のVM-IP収集ロジックを `_collect_vm_ip_maps` ヘルパーに抽出して `check-ip` と `check-acl` で共有。VM詳細の並列取得が一部失敗したら `--fix` を自動無効化して誤削除を防ぐ。

**Tech Stack:** Python 3.13, Typer, httpx, Pydantic v2, Rich, questionary, pytest（CLAUDE.md のt-wada TDD）

設計spec: `docs/superpowers/specs/2026-05-18-network-check-acl-design.md`

---

## File Structure

| ファイル | 責務 |
|----------|------|
| `src/mdx_cli/commands/network.py` | `_INTERNAL_IP_PREFIX` 定数、`VmIpMaps`、`_collect_vm_ip_maps`、`_is_host_mask`、`check-ip` 改修、`check-acl` 新規 |
| `tests/test_commands/test_network.py` | 上記のテスト追加 |
| `README.md` | `check-acl` と `check-ip --fix` の説明追記 |

API層（`api/endpoints/networks.py`）は `list_segments` / `list_acls` / `delete_acl` / `list_dnats` / `delete_dnat` / `list_assignable_ips` が既存のため変更不要。

## 実装メモ

- `parallel_get` は `check-ip` 内で関数内importされている。`_collect_vm_ip_maps` ではモジュールトップでimportし、テストから `patch("mdx_cli.commands.network.parallel_get")` でモックできるようにする。
- ACLの `dst_mask` はAPIレスポンスの形式が一定でない（`acl.py` のデフォルトは `255.255.255.255`、既存テストデータは `32`）。ホスト指定判定は `_is_host_mask` で `255.255.255.255` と `32` の両形式に対応する。
- `--json` と `--fix` が同時指定された場合は、JSON出力を優先し `--fix` は無視する（JSONモードでは questionary 対話を出せないため）。

---

## Task 1: `_collect_vm_ip_maps` ヘルパー

**Files:**
- Modify: `src/mdx_cli/commands/network.py`（import追加、定数・NamedTuple・ヘルパー追加）
- Test: `tests/test_commands/test_network.py`

- [ ] **Step 1: マップ構築の失敗テストを書く**

`tests/test_commands/test_network.py` の冒頭importを以下に置き換える:

```python
import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.network import app, _collect_vm_ip_maps
from mdx_cli.models.network import DNAT, Segment, SegmentSummary
from mdx_cli.models.vm import VM
```

ファイル末尾に追加:

```python
def test_collect_vm_ip_maps_builds_maps():
    vms = [VM(uuid="vm-1", name="web-1", status="PowerON")]
    detail = {
        "service_networks": [
            {"global_ip": "203.0.113.10", "ipv4_address": ["10.15.0.5"]}
        ]
    }
    with patch("mdx_cli.commands.network.list_vms", return_value=vms), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[detail]), \
         patch("mdx_cli.commands.network.CredentialStore"):
        maps = _collect_vm_ip_maps(None, "proj-1", json_mode=True)
    assert maps.private_ip_to_vm == {"10.15.0.5": "web-1"}
    assert maps.global_ip_to_vm == {"203.0.113.10": "VM: web-1"}
    assert maps.partial_failure is False
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_collect_vm_ip_maps_builds_maps -v`
Expected: FAIL（`ImportError: cannot import name '_collect_vm_ip_maps'`）

- [ ] **Step 3: 定数・NamedTuple・ヘルパーを実装**

`src/mdx_cli/commands/network.py` の冒頭importを以下に置き換える:

```python
import json
from typing import NamedTuple

import typer
from rich.status import Status

from mdx_cli.api.endpoints.networks import (
    get_segment_summary,
    list_assignable_ips,
    list_dnats,
    list_segments,
)
from mdx_cli.api.endpoints.vms import get_vm, list_vms
from mdx_cli.api.parallel import parallel_get
from mdx_cli.api.spinner import _console as spin_console, stop_active_spinner
from mdx_cli.commands._common import get_client, resolve_project_id, resolve_segment_id
from mdx_cli.credentials.store import CredentialStore
from mdx_cli.output.formatting import console, render
from mdx_cli.output.tables import SEGMENT_COLUMNS, SEGMENT_SUMMARY_COLUMNS
from mdx_cli.settings import Settings

from mdx_cli.commands.acl import app as acl_app
from mdx_cli.commands.dnat import app as dnat_app
```

`app.add_typer(dnat_app, name="dnat")` の行の直後に、定数とヘルパーを追加:

```python
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
    results = parallel_get(
        settings.base_url, token, paths,
        max_concurrent=50, on_progress=on_progress,
        return_exceptions=True,
    )
    if status_display:
        status_display.stop()

    global_ip_to_vm: dict[str, str] = {}
    private_ip_to_vm: dict[str, str] = {}
    for v, data in zip(active_vms, results):
        for net in data.get("service_networks", []):
            gip = net.get("global_ip", "")
            if gip:
                global_ip_to_vm[gip] = f"VM: {v.name}"
            for pip in net.get("ipv4_address", []):
                private_ip_to_vm[pip] = v.name
    return VmIpMaps(global_ip_to_vm, private_ip_to_vm, False)
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_collect_vm_ip_maps_builds_maps -v`
Expected: PASS

- [ ] **Step 5: partial_failure 検出の失敗テストを書く**

`tests/test_commands/test_network.py` 末尾に追加:

```python
def test_collect_vm_ip_maps_detects_partial_failure():
    vms = [VM(uuid="vm-1", name="web-1", status="PowerON")]
    with patch("mdx_cli.commands.network.list_vms", return_value=vms), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[RuntimeError("boom")]), \
         patch("mdx_cli.commands.network.CredentialStore"):
        maps = _collect_vm_ip_maps(None, "proj-1", json_mode=True)
    assert maps.partial_failure is True
    assert maps.private_ip_to_vm == {}
```

- [ ] **Step 6: テストを実行して失敗を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_collect_vm_ip_maps_detects_partial_failure -v`
Expected: FAIL（`data.get` で `AttributeError`、または `partial_failure` が `False`）

- [ ] **Step 7: 例外判定を実装**

`_collect_vm_ip_maps` の結果ループを以下に置き換える（`for v, data in zip(...)` ブロックと `return`）:

```python
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
```

- [ ] **Step 8: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py -v`
Expected: 全PASS

- [ ] **Step 9: コミット**

```bash
git add src/mdx_cli/commands/network.py tests/test_commands/test_network.py
git commit -m "feat: VM-IPマップ収集ヘルパー _collect_vm_ip_maps を追加"
```

---

## Task 2: `check-ip` をヘルパー利用にリファクタ

`check-ip` には既存テストが無いため、まず現状の挙動を固定する特性化テストを書いてからリファクタする。

**Files:**
- Modify: `src/mdx_cli/commands/network.py:71-169`（`check_ip` 関数）
- Test: `tests/test_commands/test_network.py`

- [ ] **Step 1: check-ip の特性化テストを書く**

`tests/test_commands/test_network.py` 末尾に追加:

```python
def test_check_ip_table_output():
    """check-ip 表示の特性化テスト（リファクタ前の挙動を固定）"""
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=["203.0.113.22"]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=[
             DNAT(uuid="d-1", pool_address="203.0.113.10", segment="s", dst_address="10.15.0.5")
         ]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "203.0.113.11", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    assert "203.0.113.11" in result.output  # VM割当IP
    assert "203.0.113.10" in result.output  # DNAT IP
    assert "203.0.113.22" in result.output  # 未使用IP
    assert "web-1" in result.output
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_check_ip_table_output -v`
Expected: FAIL（現状 check-ip は `parallel_get` を関数内importしており `mdx_cli.commands.network.parallel_get` のモックが効かず、実APIアクセスで401）。Step 3のリファクタで `_collect_vm_ip_maps`（トップレベルimport）経由に変わりモック可能になる

- [ ] **Step 3: check_ip 関数をヘルパー利用にリファクタ**

`src/mdx_cli/commands/network.py` の `check_ip` 関数全体（`@app.command("check-ip")` から関数末尾まで）を以下に置き換える:

```python
@app.command("check-ip")
def check_ip(
    project_id: str = typer.Option(None, "--project-id", "-p", help="プロジェクトID（省略時は選択済みを使用）", envvar="MDX_PROJECT_ID"),
    json_mode: bool = typer.Option(False, "--json", help="JSON出力"),
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

    # DNATの宛先IPからVM名を逆引き
    dnat_map: dict[str, str] = {}
    for d in dnats:
        vm_name = private_ip_to_vm.get(d.dst_address, "")
        if vm_name:
            dnat_map[d.pool_address] = f"DNAT → {d.dst_address} ({vm_name})"
        else:
            dnat_map[d.pool_address] = f"DNAT → {d.dst_address}"

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
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py -v`
Expected: 全PASS（特性化テストが通り続ける）

- [ ] **Step 5: コミット**

```bash
git add src/mdx_cli/commands/network.py tests/test_commands/test_network.py
git commit -m "refactor: check-ip のVM-IP収集を _collect_vm_ip_maps に集約"
```

---

## Task 3: `check-ip --fix`

死んだVM宛のDNAT（`dst_address` が `10.15.` 始まりかつ現存VMに無い）を `--fix` で削除する。

**Files:**
- Modify: `src/mdx_cli/commands/network.py`（`check_ip` 関数）
- Test: `tests/test_commands/test_network.py`

- [ ] **Step 1: --fix の失敗テストを書く**

`tests/test_commands/test_network.py` 末尾に追加:

```python
def test_check_ip_fix_deletes_orphan_dnat():
    """--fix で死んだVM宛DNATを削除する"""
    dnats = [
        DNAT(uuid="d-alive", pool_address="203.0.113.10", segment="s", dst_address="10.15.0.5"),
        DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99"),
    ]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "d-hole"
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_check_ip_fix_deletes_orphan_dnat -v`
Expected: FAIL（`--fix` オプションが無く `No such option: --fix`）

- [ ] **Step 3: --fix を実装**

`src/mdx_cli/commands/network.py` 冒頭importに `questionary` と `delete_dnat` を追加する。import の `import json` の下に `import questionary` を足し、`from mdx_cli.api.endpoints.networks import (...)` に `delete_dnat` を加える:

```python
import json

import questionary
import typer
from rich.status import Status

from mdx_cli.api.endpoints.networks import (
    delete_dnat,
    get_segment_summary,
    list_assignable_ips,
    list_dnats,
    list_segments,
)
```

`check_ip` 関数のシグネチャに `--fix` を追加。`json_mode` 引数の下に1行足す:

```python
    json_mode: bool = typer.Option(False, "--json", help="JSON出力"),
    fix: bool = typer.Option(False, "--fix", help="死んだVM宛のDNATを削除"),
) -> None:
```

`check_ip` 関数のDNAT逆引きブロックを以下に置き換える（`dnat_map` 構築部分）:

```python
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
```

`check_ip` 関数末尾（`console.print()` の後）に `--fix` 処理を追加:

```python

    if fix and not json_mode:
        if vm_maps.partial_failure:
            console.print("[yellow]⚠ VM詳細の取得に一部失敗したため --fix を無効化しました。再実行してください[/yellow]")
            return
        if not hole_dnats:
            console.print("[green]穴（死んだVM宛のDNAT）はありません[/green]")
            return
        console.print(f"[bold red]{len(hole_dnats)}件の穴DNATを削除します:[/bold red]")
        for d in hole_dnats:
            console.print(f"  {d.pool_address} → {d.dst_address} [dim]({d.uuid})[/dim]")
        if not questionary.confirm(f"{len(hole_dnats)}件を削除しますか？").unsafe_ask():
            raise typer.Abort()
        deleted, failed = 0, 0
        for d in hole_dnats:
            try:
                delete_dnat(client, d.uuid)
                deleted += 1
            except Exception as e:
                console.print(f"[red]  削除失敗 {d.uuid}: {e}[/red]")
                failed += 1
        stop_active_spinner()
        console.print(f"\n削除: {deleted}件  失敗: {failed}件")
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_check_ip_fix_deletes_orphan_dnat -v`
Expected: PASS

- [ ] **Step 5: 部分失敗時の --fix 抑止の失敗テストを書く**

`tests/test_commands/test_network.py` 末尾に追加:

```python
def test_check_ip_fix_suppressed_on_partial_failure():
    """VM詳細取得が一部失敗したら --fix を抑止する"""
    dnats = [
        DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99"),
    ]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[RuntimeError("boom")]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_not_called()
    assert "無効化" in result.output
```

- [ ] **Step 6: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_check_ip_fix_suppressed_on_partial_failure -v`
Expected: PASS（Step 3で `partial_failure` チェックを実装済みのため通る）

- [ ] **Step 7: コミット**

```bash
git add src/mdx_cli/commands/network.py tests/test_commands/test_network.py
git commit -m "feat: check-ip に --fix を追加（死んだVM宛DNATを削除）"
```

---

## Task 4: `check-acl` 表示

プロジェクト全体のACLを走査し、`10.15.*` 宛のACLを「穴 / 生存 / 範囲指定」に分類して表示する。

**Files:**
- Modify: `src/mdx_cli/commands/network.py`（`_is_host_mask` ヘルパーと `check_acl` コマンドを追加）
- Test: `tests/test_commands/test_network.py`

- [ ] **Step 1: check-acl 分類の失敗テストを書く**

`tests/test_commands/test_network.py` 冒頭の import に `ACL` を追加:

```python
from mdx_cli.models.network import ACL, DNAT, Segment, SegmentSummary
```

ファイル末尾にACL生成ヘルパーとテストを追加:

```python
_ACL_BASE = {
    "uuid": "acl-x",
    "protocol": "TCP",
    "src_address": "0.0.0.0",
    "src_mask": "0.0.0.0",
    "src_port": "Any",
    "dst_address": "10.15.0.5",
    "dst_mask": "255.255.255.255",
    "dst_port": "22",
}


def _make_acl(**overrides):
    return ACL(**{**_ACL_BASE, **overrides})


def test_check_acl_classifies_holes_alive_range():
    """穴・生存・範囲指定を分類して表示する"""
    acls = [
        _make_acl(uuid="acl-hole", dst_address="10.15.0.99", dst_mask="255.255.255.255"),
        _make_acl(uuid="acl-alive", dst_address="10.15.0.5", dst_mask="255.255.255.255"),
        _make_acl(uuid="acl-range", dst_address="10.15.0.0", dst_mask="255.255.0.0"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network.list_acls", return_value=acls), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    assert "10.15.0.99" in result.output  # 穴
    assert "10.15.0.5" in result.output   # 生存
    assert "10.15.0.0" in result.output   # 範囲
    assert "穴" in result.output
    assert "web-1" in result.output       # 生存にVM名


def test_check_acl_excludes_non_internal_dst():
    """10.15. 以外の dst（Any・外部IP）は一覧に出さない"""
    acls = [
        _make_acl(uuid="acl-any", dst_address="0.0.0.0", dst_mask="0.0.0.0"),
        _make_acl(uuid="acl-ext", dst_address="8.8.8.8", dst_mask="255.255.255.255"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network.list_acls", return_value=acls), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    assert "8.8.8.8" not in result.output


def test_check_acl_json():
    """--json で穴の status を出力する"""
    acls = [_make_acl(uuid="acl-hole", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network.list_acls", return_value=acls), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["status"] == "hole"
    assert data[0]["acl_id"] == "acl-hole"
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_check_acl_classifies_holes_alive_range -v`
Expected: FAIL（`check-acl` コマンドが無く `No such command 'check-acl'`）

- [ ] **Step 3: `_is_host_mask` と `check_acl` を実装**

`src/mdx_cli/commands/network.py` 冒頭の networks import に `list_acls` と `delete_acl` を追加:

```python
from mdx_cli.api.endpoints.networks import (
    delete_acl,
    delete_dnat,
    get_segment_summary,
    list_acls,
    list_assignable_ips,
    list_dnats,
    list_segments,
)
```

`_collect_vm_ip_maps` 関数の後に `_is_host_mask` を追加:

```python
def _is_host_mask(mask: str) -> bool:
    """単一ホスト指定のマスクか（255.255.255.255 / 32 / /32 形式に対応）。"""
    return mask.strip().lstrip("/") in ("255.255.255.255", "32")
```

ファイル末尾に `check_acl` コマンドを追加:

```python
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

    # セグメントごとにACLを分類: [(segment, [(acl, status, vm_name), ...]), ...]
    seg_results: list = []
    holes: list = []  # (segment, acl) — 穴
    for seg in segments:
        acls = list_acls(client, seg.uuid)
        stop_active_spinner()
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
        out = []
        for seg, classified in seg_results:
            for acl, status, vm_name in classified:
                out.append({
                    "segment_id": seg.uuid,
                    "segment_name": seg.name,
                    "acl_id": acl.uuid,
                    "protocol": acl.protocol,
                    "dst_address": acl.dst_address,
                    "dst_mask": acl.dst_mask,
                    "status": status,
                    "vm_name": vm_name,
                })
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

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

    if fix:
        if vm_maps.partial_failure:
            console.print("[yellow]⚠ VM詳細の取得に一部失敗したため --fix を無効化しました。再実行してください[/yellow]")
            return
        if not holes:
            console.print("[green]穴はありません[/green]")
            return
        if not questionary.confirm(f"{len(holes)}件の穴ACLを削除しますか？").unsafe_ask():
            raise typer.Abort()
        deleted, failed = 0, 0
        for seg, acl in holes:
            try:
                delete_acl(client, acl.uuid)
                deleted += 1
            except Exception as e:
                console.print(f"[red]  削除失敗 {acl.uuid}: {e}[/red]")
                failed += 1
        stop_active_spinner()
        console.print(f"\n削除: {deleted}件  失敗: {failed}件")
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add src/mdx_cli/commands/network.py tests/test_commands/test_network.py
git commit -m "feat: mdx network check-acl を追加（死んだVM宛ACLの検出）"
```

---

## Task 5: `check-acl --fix` のテスト

`--fix` の実装はTask 4で済んでいる。削除と部分失敗抑止のテストを追加する。

**Files:**
- Test: `tests/test_commands/test_network.py`

- [ ] **Step 1: --fix 削除のテストを書く**

`tests/test_commands/test_network.py` 末尾に追加:

```python
def test_check_acl_fix_deletes_holes():
    """--fix で穴ACLを削除する"""
    acls = [
        _make_acl(uuid="acl-hole", dst_address="10.15.0.99"),
        _make_acl(uuid="acl-alive", dst_address="10.15.0.5"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network.list_acls", return_value=acls), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "acl-hole"
```

- [ ] **Step 2: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py::test_check_acl_fix_deletes_holes -v`
Expected: PASS

- [ ] **Step 3: 部分失敗時の抑止テストを書く**

`tests/test_commands/test_network.py` 末尾に追加:

```python
def test_check_acl_fix_suppressed_on_partial_failure():
    """VM詳細取得が一部失敗したら --fix を抑止する"""
    acls = [_make_acl(uuid="acl-hole", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network.list_acls", return_value=acls), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[RuntimeError("boom")]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.CredentialStore"), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_not_called()
    assert "無効化" in result.output
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/test_commands/test_network.py -v`
Expected: 全PASS

- [ ] **Step 5: フルテストスイートを実行**

Run: `uv run pytest`
Expected: 全PASS（既存テストへの影響なし）

- [ ] **Step 6: コミット**

```bash
git add tests/test_commands/test_network.py
git commit -m "test: check-acl --fix の削除と部分失敗抑止のテストを追加"
```

---

## Task 6: README 更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README に check-acl と check-ip --fix を追記**

`README.md` の `mdx network check-ip` を説明している箇所を探す（`grep -n "check-ip" README.md`）。`check-ip` の説明の近くに、次の内容を追記する。実際の見出しレベルと文体は周囲の記述に合わせること:

```markdown
### グローバルIP・ACLの点検

```bash
mdx network check-ip          # グローバルIPv4の使用状況
mdx network check-ip --fix    # 死んだVM宛のDNATを削除
mdx network check-acl         # 死んだVM宛のACL（穴）を検出
mdx network check-acl --fix   # 死んだVM宛のACLを削除
```

`check-acl` はプロジェクト全体のACLを走査し、宛先（`10.15.*`）が現存しない
VM を指すルールを「穴」として検出する。VMを削除してもACL/DNATは残るため、
IPが再割当されると意図しない通信を許可してしまう。`--fix` で一括削除できる。

VM詳細の取得に一部失敗した場合、穴判定が不正確になるため `--fix` は自動的に
無効化される（誤削除防止）。
```

- [ ] **Step 2: コミット**

```bash
git add README.md
git commit -m "docs: README に check-acl と check-ip --fix を追記"
```

---

## 完了条件

- [ ] `uv run pytest` が全PASS
- [ ] `mdx network check-acl` / `check-acl --fix` / `check-ip --fix` が動作
- [ ] 部分失敗時に `--fix` が抑止される
- [ ] README 更新済み
