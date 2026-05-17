# `mdx network check-acl` と `check-ip --fix` 設計

- 日付: 2026-05-18
- ブランチ: `feat/network-check-acl`

## 背景・目的

VM を削除しても、その VM を宛先にしていた ACL ルールや DNAT は残る。
残ったルールは「穴」になる:

- ACL: 死んだ VM のプライベート IP 宛の許可ルールが残る。その IP が別の VM に
  再割当されると、意図しない通信が許可される。
- DNAT: グローバル IP → 死んだ VM のプライベート IP のマッピングが残る。IP が
  再利用されると誤転送になる。

既存の `mdx network check-ip` はグローバル IP の使用状況を一覧表示するだけで、
こうした「穴」を検出・修復する手段がない。本機能でそれを補う。

## 確定要件

1. **新規コマンド `mdx network check-acl`**
   - スコープ: プロジェクト全体（全セグメントの ACL を走査）
   - 照合対象: ACL の `dst`（宛先）のみ
   - 表示対象: `dst_address` が `10.15.` で始まる ACL のみ（MDX 内部ネットワーク）。
     Any（`0.0.0.0`）や外部 IP 宛の ACL は表示しない。
   - `--fix` で穴を一括削除（通常は表示のみ）
2. **既存コマンド `mdx network check-ip` に `--fix` を追加**
   - 削除対象は「死んだ VM 宛の DNAT」のみ。未使用グローバル IP は触らない。
3. 両コマンドとも `--json` / `--project-id` をサポート（既存コマンドの慣習）

## 非対象（YAGNI）

- 未使用グローバル IP のプロジェクトからの解放
- ACL の `src`（送信元）側の照合
- セグメント単位スコープのオプション（プロジェクト全体のみ）
- 他プロジェクトをまたぐ監査

## アーキテクチャ

すべて `src/mdx_cli/commands/network.py` 内に収める（既存の `check-ip` と同居）。

### 新規定数

```python
_INTERNAL_IP_PREFIX = "10.15."  # MDX 内部ネットワーク。変更時はここだけ
```

### 新規ヘルパー `_collect_vm_ip_maps`

```python
def _collect_vm_ip_maps(client, pid: str, json_mode: bool) -> VmIpMaps:
    """アクティブ VM を並列取得し、IP マップを構築する。"""
```

返す内容（`VmIpMaps` は `NamedTuple`）:

- `global_ip_to_vm: dict[str, str]` — グローバル IP → `VM: <name>`
- `private_ip_to_vm: dict[str, str]` — プライベート IP → VM 名
- `partial_failure: bool` — VM 詳細の並列取得で 1 台以上失敗したか

現状 `check-ip` の `network.py:93-130` にインライン展開されている VM 詳細取得・
マップ構築ロジックをここへ抽出する。`check-ip` 自身もこのヘルパーを使う形に
リファクタし、重複を排除する。

並列取得は `parallel_get(..., return_exceptions=True)`（v1.4.0 で追加済み）を
使い、例外を捕捉して `partial_failure` に反映する。

### コマンド構成

```
mdx network check-ip   [--fix] [--json] [--project-id]   # 改修
mdx network check-acl  [--fix] [--json] [--project-id]   # 新規
```

## 判定ロジック

### 穴判定（dst のみ）

| 種別 | VM 宛候補の条件 | 穴の条件 |
|------|----------------|----------|
| ACL  | `dst_mask == "255.255.255.255"`（ホスト指定）かつ `dst_address` が `10.15.` 始まり | 候補かつ `private_ip_to_vm` に無い |
| DNAT | `dst_address` が `10.15.` 始まり（DNAT にマスクは無い） | 候補かつ `private_ip_to_vm` に無い |

### `check-acl` の ACL 3 分類

`dst_address` が `10.15.` 始まりの ACL のみ表示し、次の 3 つに分類する:

- **穴**: ホスト指定（`dst_mask == 255.255.255.255`）かつ現存 VM に無い → 赤で強調
- **生存**: ホスト指定かつ現存 VM にある → VM 名を併記
- **範囲指定**: `dst_mask` が `255.255.255.255` でない（サブネット宛）→ 単一 VM 宛では
  ないので穴判定の対象外。参考情報として淡色表示

`dst_address` が `10.15.` で始まらない ACL（Any・外部 IP 宛）は一覧に出さない。

## 出力

### `check-acl`（テーブル表示・デフォルト）

セグメントごとにグルーピングして表示する。

```
セグメント: default-segment (xxxx-uuid)

  ⚠ 穴   TCP   0.0.0.0/0 :Any  →  10.15.20.143/32 :443   (VM不在)
    生存  TCP   0.0.0.0/0 :Any  →  10.15.17.83/32  :22    (VM: 1-aida-serv)
    範囲  TCP   0.0.0.0/0 :Any  →  10.15.0.0/16    :Any

  合計: 3  穴: 1  生存: 1  範囲: 1
```

末尾にプロジェクト全体の合計（穴の総数）を表示。

### `check-acl --json`

```json
[
  {
    "segment_id": "xxxx-uuid",
    "segment_name": "default-segment",
    "acl_id": "yyyy-uuid",
    "protocol": "TCP",
    "dst_address": "10.15.20.143",
    "dst_mask": "255.255.255.255",
    "status": "hole",          // hole | alive | range
    "vm_name": null
  }
]
```

### `check-ip`

表示は現状維持。`--fix` 指定時のみ、末尾に穴 DNAT の削除フローを追加する。

## `--fix` の挙動

1. 穴（`check-acl` なら穴 ACL、`check-ip` なら穴 DNAT）の一覧を表示
2. 穴が 0 件なら「穴はありません」と表示して終了
3. `questionary.confirm("N 件の穴を削除しますか？")` で確認（CLAUDE.md の UI パターン）
4. 拒否なら `typer.Abort()`
5. 承認なら逐次 `delete_acl` / `delete_dnat`（スピナー表示）
6. 削除結果のサマリーを表示（成功 N 件 / 失敗 M 件）

削除は件数が少ない想定なので逐次実行で十分（並列化しない）。

## エラー処理（安全策）

### 部分失敗時の `--fix` 抑止 ⚠️

VM 詳細の並列取得が一部失敗すると、その VM の IP が `private_ip_to_vm` から漏れ、
**正当なルールを穴と誤判定し、`--fix` で誤削除する**恐れがある。

対策: `_collect_vm_ip_maps` が `partial_failure=True` を返したら、

- 警告を表示する（「N 台の VM 詳細取得に失敗。穴判定が不正確な可能性」）
- `--fix` が指定されていても**自動的に無効化**し、表示のみに降格する
- ユーザーには再実行を促す

### その他

- セグメント / ACL / DNAT の取得失敗: 通常の httpx 例外を伝播（既存コマンドと同じ）
- `--fix` の個別削除失敗: 1 件失敗しても残りは続行し、失敗を末尾サマリーに集約

## テスト方針（t-wada TDD）

`respx` でセグメント / ACL / DNAT / VM API をモックする。テスト追加先は
`tests/test_commands/test_network.py`（無ければ新規）。

1. `_collect_vm_ip_maps`: アクティブ VM からマップを正しく構築する
2. `_collect_vm_ip_maps`: VM 詳細取得が一部失敗したら `partial_failure=True`
3. `check-acl`: 穴 / 生存 / 範囲指定を正しく分類する
4. `check-acl`: `10.15.` 以外の dst（Any・外部 IP）は一覧に出さない
5. `check-acl --fix`: 確認後に穴 ACL を `delete_acl` する
6. `check-acl --fix`: 部分失敗時は `--fix` が抑止され削除されない
7. `check-ip --fix`: 死んだ VM 宛 DNAT を `delete_dnat` する
8. `check-ip --fix`: 部分失敗時は `--fix` が抑止される

`questionary.confirm` はモックする（CLAUDE.md のテスト方針）。

## 影響ファイル

| ファイル | 変更 |
|----------|------|
| `src/mdx_cli/commands/network.py` | `_INTERNAL_IP_PREFIX`、`_collect_vm_ip_maps`、`check-acl` 追加。`check-ip` を `--fix` 対応＋ヘルパー利用にリファクタ |
| `tests/test_commands/test_network.py` | 上記テストを追加（無ければ新規作成） |
| `README.md` | `check-acl` の説明と `check-ip --fix` を追記 |

API 層（`api/endpoints/networks.py`）は `list_acls` / `delete_acl` / `list_dnats` /
`delete_dnat` / `list_segments` が既にあるため変更不要。
