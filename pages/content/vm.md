# VMを操作する

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

### デプロイ

対話式とワンライナーの両方に対応。引数を指定した分はスキップ、未指定分だけ対話で聞きます。

```bash
# 全て対話式
mdx vm deploy

# 全引数指定（スクリプトから対話なし実行）
mdx vm deploy \
  -t "Ubuntu 22.04" \
  -n "worker-{a-e}-{0-9}" \
  --pack-type cpu \
  --pack-num 3 \
  --disk 40 \
  --service-level spot \
  -k ~/.ssh/id_ed25519.pub \
  --power-on \
  -y \
  --no-wait

# 一部だけ指定（残りは対話）
mdx vm deploy -n my-vm --pack-num 10
```

| オプション | 説明 |
|-----------|------|
| `-t` / `--template` | テンプレート名（部分一致） |
| `-n` / `--name` | VM名（パターン対応） |
| `--pack-type` | `cpu` / `gpu` |
| `--pack-num` | パック数 |
| `--disk` | ディスクサイズ (GB) |
| `--service-level` | `spot` / `guarantee` |
| `-k` / `--key` | SSH公開鍵のパス |
| `--power-on` | デプロイ後に自動起動 |
| `-y` / `--yes` | 確認をスキップ |
| `--no-wait` | タスク完了を待たない |

#### バッチ作成

VM 名にパターンを指定すると複数台を一括作成できます。

| パターン | 展開結果 | 台数 | リクエスト数 |
|---------|---------|------|-------------|
| `my-vm` | my-vm | 1 | 1 |
| `my-vm-{0-9}` | my-vm-0 ~ my-vm-9 | 10 | **1**（API側で展開） |
| `crawler-{a-g}-{0-9}` | crawler-a-0 ~ crawler-g-9 | 70 | **7**（アルファベット部分のみ展開） |
| `node-{00-05}` | node-00 ~ node-05 | 6 | 6（ゼロ埋めはクライアント展開） |
| `vm-{1-99}` | vm-1 ~ vm-99 | 99 | 99（複数桁はクライアント展開） |

単一桁数値範囲（`{0-9}`, `{1-9}`, `{3-7}` 等）は MDX API の `[N-M]` 記法に変換されサーバー側で展開されます。リクエスト数が大幅に削減され、レート制限を回避できます。

### 起動・停止・削除（パターン対応、5並列）

全操作でパターン指定による一括操作に対応。5並列・リトライ付き。

```bash
# 起動
mdx vm start web-server
mdx vm start "worker-*" -s spot

# 正常シャットダウン
mdx vm shutdown "worker-*"

# 強制停止
mdx vm stop "worker-*"

# 再起動 / リセット
mdx vm reboot "worker-*"
mdx vm reset "worker-*"

# 削除（稼働中VMは自動停止してから削除）
mdx vm destroy "test-*"

# 範囲パターン
mdx vm stop "worker-{a-c}-*"
```

### 名前を変更する

```bash
mdx vm rename my-vm-01 new-vm-01
mdx vm rename "worker-*" --suffix=-old
```

単一VMは新しい名前を指定します。一括変更は `--suffix` で現在名に文字列を追加します。

### 構成変更（対話式、パターン対応）

VMのパック数・ディスクサイズを変更。稼働中VMは自動停止します。パターン指定で複数台を一括変更可能。

```bash
mdx vm reconfigure my-vm              # 名前指定
mdx vm reconfigure                    # 一覧から選択
mdx vm reconfigure "worker-*"         # パターンで複数台一括
mdx vm reconfigure "worker-{a-c}-*"   # 範囲パターン
```

複数台指定時の制約：
- `pack_type`（cpu / gpu）が全VMで一致していること
- ディスク本数が全VMで一致していること
- 新しい `pack_num` と各ディスクの新容量は全VM共通で適用（`device_key` と `segment` は各VMの現状を保持）

### リソース一覧

```bash
mdx vm resources                     # 全VM
mdx vm resources "worker-*"          # パターン指定
mdx vm resources "node-{00-05}"      # 範囲パターン
mdx vm resources --json              # JSON出力
```

VMごとのパック・CPU・メモリ・GPU・ディスク容量を一覧表示します。

```
┏━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━┳━━━━━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ 名前      ┃ 状態     ┃ パック   ┃ CPU ┃ メモリ   ┃ GPU ┃ ディスク       ┃ 合計(GB) ┃
┡━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━╇━━━━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ worker-00 │ PowerON  │ cpu x 16 │ 16  │ 24.1 GB  │ 0   │ 100 GB         │ 100      │
│ worker-01 │ PowerOFF │ cpu x 16 │ 16  │ 24.1 GB  │ 0   │ 100 GB, 500 GB │ 600      │
│ gpu-node0 │ PowerON  │ gpu x 2  │ 36  │ 115.2 GB │ 2   │ 200 GB         │ 200      │
└───────────┴──────────┴──────────┴─────┴──────────┴─────┴────────────────┴──────────┘
合計: 3台 / 900 GB
```

VM詳細APIを台数分呼ぶため、台数が多いときはパターンで絞り込むと速くなります。

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
