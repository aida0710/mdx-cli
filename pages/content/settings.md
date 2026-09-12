# 出力・設定・シェル補完

## 出力形式

デフォルトは、テーブル表示。`--json` フラグで JSON 出力に切り替え。API 取得中はスピナーが表示されます。

```bash
mdx vm list                # テーブル表示（スピナー付き）
mdx vm list --json         # JSON出力
mdx vm list --json | jq .  # jq と組み合わせ
```

## 共通オプション

| オプション | 説明 |
|-----------|------|
| `--verbose` / `-v` | API リクエスト/レスポンスの詳細ログ表示 |
| `--json` | 対応するサブコマンドに指定してJSON出力 |
| `--project-id` / `-p` | 対応するサブコマンドに指定してプロジェクトを選択 |

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
