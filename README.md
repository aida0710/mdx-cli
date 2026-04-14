# mdx-cli

[MDX 1](https://mdx.jp/) クラウドインフラプラットフォームの非公式CLIツール。

Web ポータル (oprpl.mdx.jp) の操作をコマンドラインから実行できます。VM の一括作成・起動・停止、SSH接続、ネットワーク管理、DNAT/ACL 設定などに対応。

## インストール

```bash
uv tool install .
```

## クイックスタート

```bash
# 1. ログイン（Shibboleth SSO、OTP必要）
# MDX Local Auth のみ対応、学認は非対応
mdx auth login

# 2. プロジェクトを選択（一度だけ）
mdx project select

# 3. VM一覧を見る
mdx vm list

# 4. VMにSSH接続
mdx vm ssh my-vm-01
```

## コマンド一覧

```
mdx auth          認証管理
mdx project       プロジェクト管理
mdx vm            仮想マシン管理
mdx network       ネットワーク管理
  mdx network segment  セグメント管理
  mdx network acl      ACL管理
  mdx network dnat     DNAT管理
  mdx network ips      割当可能グローバルIP一覧
  mdx network check-ip グローバルIP使用状況チェック
mdx template      テンプレート管理
mdx task          タスク・操作履歴管理
  mdx task list    操作履歴一覧
  mdx task status  タスク状態確認
  mdx task wait    タスク完了待機
```

## 認証

Shibboleth SSO 経由でログインします。ユーザー名・パスワード・TOTP の入力が必要です。

```bash
mdx auth login     # ログイン
mdx auth status    # 認証状態を確認
mdx auth logout    # ログアウト（全クレデンシャル削除）
```

- ユーザー名とパスワードは keyring（macOS Keychain 等）に保存
- 2回目以降のログインは OTP の入力のみ
- トークン期限切れ時は自動で再ログイン（OTP だけプロンプト）

## プロジェクト

```bash
mdx project list       # プロジェクト一覧
mdx project summary    # VM数・リソース・ストレージ使用量
mdx project select     # 使用するプロジェクトを選択（以降 --project-id 不要）
mdx project show <id>  # プロジェクト詳細
mdx project storage <id>  # ストレージ情報
mdx project keys <id>  # アクセスキー一覧
```

`project summary` の表示例:

```
VM（スポット）:
  稼働中: 5  停止: 2  未割当: 13  合計: 20

VMディスク:
  使用: 1,500 GB / 5,000 GB（残り 3,500 GB）

高速ストレージ: /fast/0/d12345678
  使用: 100.0 GB / 500.0 GB（残り 400.0 GB, 20.0%）

大容量ストレージ: /large/0/d12345678
  使用: 2,048.0 GB / 10,000.0 GB（残り 7,952.0 GB, 20.5%）

オブジェクトストレージ: /object
  使用: 512.0 GB / 5,000.0 GB（残り 4,488.0 GB, 10.2%）
```

## 仮想マシン (VM)

### 一覧・詳細

```bash
mdx vm list                    # VM一覧
mdx vm show my-vm-01           # 名前で詳細表示
mdx vm show                    # 一覧から番号選択
mdx vm list --json             # JSON出力
mdx vm list --json | jq '.[] | select(.status == "PowerON") | .name'
```

`vm show` の表示例:

```
my-vm-01
  UUID:           a1b2c3d4-e5f6-7890-abcd-ef1234567890
  状態:           PowerON
  サービスレベル: スポット仮想マシン
  OS:             Ubuntu Linux (64-bit)
  CPU:            16
  メモリ:         64.0 GB
  GPU:            0
  パック:         cpu x 16

ディスク:
  #1: 100 GB (ds-nfs-01)

ネットワーク:
  アダプタ 1:
    セグメント:   my-network-segment
    IPv4:         10.0.0.10
    グローバルIP: 203.0.113.10
```

### SSH接続

```bash
mdx vm ssh my-vm-01                    # 名前で接続（IP・ユーザー名を自動取得）
mdx vm ssh                             # 稼働中VMから一覧選択
mdx vm ssh my-vm-01 -i ~/.ssh/mdx-key  # 秘密鍵を指定
mdx vm ssh my-vm-01 -u root            # ユーザー名を指定
mdx vm ssh my-vm-01 -g                 # グローバルIPで接続
```

- SSHユーザー名はテンプレートの `login_username` から自動検出（`mdxuser`, `mdx-user01` 等）
- デフォルトはプライベートIP、`-g` でグローバルIPを使用

### デプロイ（対話式）

```bash
mdx vm deploy
```

テンプレート・セグメント・SSH鍵・リソースを対話的に選択。全入力で矢印キーによるカーソル移動・編集が可能。

#### バッチ作成

VM 名にパターンを指定すると複数台を一括作成できます。

| パターン | 展開結果 | 台数 |
|---------|---------|------|
| `my-vm` | my-vm | 1 |
| `my-vm-{0-9}` | my-vm-0 ~ my-vm-9 | 10 |
| `crawler-{a-g}-{0-9}` | crawler-a-0 ~ crawler-g-9 | 70 |
| `node-{00-05}` | node-00 ~ node-05 | 6 |

### 起動・停止・削除（パターン対応）

```bash
# 単体操作
mdx vm start web-server
mdx vm stop web-server
mdx vm destroy web-server

# glob パターンで一括操作
mdx vm stop "worker-*"
mdx vm start "worker-*" -s spot
mdx vm destroy "test-*"

# 範囲パターン
mdx vm stop "worker-{a-c}-*"
```

複数台操作時は対象一覧を表示して確認を求めます。

### CSV出力

```bash
mdx vm csv                          # 全VM
mdx vm csv "worker-*"               # パターン指定
mdx vm csv -o vm-info.csv           # ファイル出力
mdx vm csv "worker-*" -o out.csv    # 組み合わせ
```

Webポータルと同じ列構成（SERVICE_NET_1-8, STORAGE_NET_1-8）で出力します。

### その他

```bash
mdx vm start "worker-*" -s guarantee  # サービスレベル指定
mdx vm sync                          # VM情報を同期
mdx vm deploy --no-wait              # タスク完了を待たない
```

## ネットワーク

### セグメント・IP

```bash
mdx network segment list         # セグメント一覧
mdx network segment show         # セグメント詳細（一覧から選択可能）
mdx network ips                  # 割当可能グローバルIP一覧
mdx network check-ip             # グローバルIPv4 使用状況チェック
```

`check-ip` の表示例:

```
グローバルIPv4 使用状況:

  203.0.113.10  DNAT → 10.0.0.20 (db-server)
  203.0.113.11  VM: web-server
  203.0.113.12  VM: my-vm-01
  203.0.113.13  未使用
  203.0.113.14  未使用

  合計: 5  使用中: 3  未使用: 2
```

VM直接割当・DNAT経由・未使用を一覧表示。DNATの宛先からVM名も逆引き表示。並列取得で高速。

### DNAT（全て対話式）

```bash
mdx network dnat list    # DNAT一覧
mdx network dnat add     # 追加（グローバルIP一覧から選択、宛先を入力）
mdx network dnat edit    # 編集（一覧から選択、現在値をデフォルト表示）
mdx network dnat delete  # 削除（一覧から選択可能）
```

### ACL（全て対話式）

```bash
mdx network acl list     # ACL一覧（セグメント自動選択）
mdx network acl add      # 追加（プロトコル・アドレス・ポートを対話入力）
mdx network acl edit     # 編集（一覧から選択、現在値をデフォルト表示）
mdx network acl delete   # 削除（一覧から選択可能）
```

## テンプレート

```bash
mdx template list       # テンプレート一覧
mdx template show       # テンプレート詳細（一覧から選択可能）
```

## タスク・操作履歴

```bash
mdx task list              # 操作履歴一覧（最新100件）
mdx task list -n 20        # 件数指定
mdx task list -t デプロイ   # 操作種別でフィルタ（デプロイ、自動休止 等）
mdx task list -n 1000      # 最大1000件
mdx task status <task-id>  # 個別タスクの状態確認
mdx task wait <task-id>    # タスク完了まで待機
```

`task list` の表示例:

```
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ 操作種別  ┃ 対象             ┃ 状態      ┃ 開始                ┃ ユーザー┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ デプロイ  │ worker-a-0       │ Completed │ 2025-01-15 10:00:00 │ taro.y  │
│ 自動休止  │ worker-b-1       │ Completed │ 2025-01-15 09:30:00 │ system  │
│ DNATの削除│ 203.0.113.10     │ Completed │ 2025-01-15 09:00:00 │ taro.y  │
```

`task status` / `task wait` は `--no-wait` でデプロイした後にタスクIDで進捗を確認する用途です。

## 出力形式

デフォルトは、テーブル表示。`--json` フラグで JSON 出力に切り替え。API 取得中はスピナーが表示されます。

```bash
mdx vm list                # テーブル表示（スピナー付き）
mdx vm list --json         # JSON出力
mdx vm list --json | jq .  # jq と組み合わせ
```

## グローバルオプション

| オプション | 説明 |
|-----------|------|
| `--verbose` / `-v` | API リクエスト/レスポンスの詳細ログ表示 |
| `--json` | JSON 出力（各サブコマンド） |
| `--project-id` / `-p` | プロジェクト ID の明示指定 |

## 設定

| 環境変数 | デフォルト | 説明 |
|---------|----------|------|
| `MDX_BASE_URL` | `https://oprpl.mdx.jp` | API ベース URL |
| `MDX_PROJECT_ID` | - | デフォルトプロジェクト ID |
| `MDX_REQUEST_TIMEOUT` | `120` | リクエストタイムアウト（秒） |

設定ファイル: `~/.config/mdx-cli/`

## シェル補完

```bash
mdx --install-completion zsh  # 補完をインストール（bash/fish も対応）
exec zsh                      # シェルを再起動
```

## 開発

```bash
uv sync                # 依存インストール
uv run pytest -v       # テスト実行
mdx -v auth login      # デバッグモード
```
