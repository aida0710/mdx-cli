# Changelog

## v1.2.0

### 新機能
- `vm deploy` が全引数指定に対応（`-t`, `-n`, `--pack-type`, `--pack-num`, `--disk`, `--service-level`, `-k`, `--power-on`, `-y`, `--no-wait`）
- 引数指定分はスキップ、未指定分だけ対話で聞くハイブリッド方式
- スクリプトからの対話なし実行が可能に

### 改善
- POST系の並列数を50→10に調整（サーバーレート制限対策）
- GET/POSTに最大3回のリトライ機構を追加（exponential backoff: 1s/2s/4s）
- 404/500/接続エラーで自動リトライ後にエラーを報告

## v1.1.0

### 新機能
- `vm shutdown` — 正常シャットダウン（`POST /api/vm/{id}/shutdown/`）
- `vm reboot` — 再起動（`POST /api/vm/{id}/reboot/`）
- `vm reset` — リセット（`POST /api/vm/{id}/reset/`）
- `vm reconfigure` — VM構成変更（パック数・ディスクサイズ変更、対話式、停止中VMが必要）
- 全VM操作を最大50並列化（deploy / start / stop / shutdown / reboot / reset / destroy / csv / check-ip）

### バグ修正
- `vm destroy` で `task_id` が文字列で返る場合のパース修正
- `vm destroy` で稼働中VMを自動停止し、PowerOFF完了を待ってから削除実行
- パターン指定（`*`）のヘルプにシェルクォート必須の注記を追加

### UX改善
- サブコマンド未指定時にヘルプを表示（`no_args_is_help=True`）
- `vm stop` のヘルプを「強制停止」に明確化（`shutdown` との区別）

## v1.0.0

初期リリース。

### 認証
- Shibboleth SSO 経由のログイン（MDX Local Auth）
- ユーザー名・パスワードを keyring に保存、2回目以降はOTPのみ
- トークン期限切れ時の自動再ログイン

### プロジェクト
- `project list` — プロジェクト一覧
- `project select` — 使用プロジェクトを番号選択して保存
- `project summary` — VM数・リソース・ストレージ使用量の概要表示
- `project show` / `storage` / `keys`

### 仮想マシン
- `vm list` / `vm show` — 一覧・詳細表示（名前 / UUID / 番号選択）
- `vm deploy` — 対話式デプロイ（テンプレート・セグメント・SSH鍵を選択、CPU/GPUパック選択・スペック自動計算）
- `vm start` / `vm stop` / `vm destroy` — 起動・強制停止・削除（パターン対応）
- `vm ssh` — VM名でSSH接続（IP・ユーザー名を自動取得、`-i` 秘密鍵指定）
- `vm csv` — VM情報CSVダウンロード（Webポータルと同じ形式）
- `vm sync` — VM情報同期
- VM名パターンでバッチ作成: `name-{0-9}`, `name-{a-g}-{0-9}` 等

### ネットワーク
- `network segment list` / `show` — セグメント一覧・詳細
- `network ips` — 割当可能グローバルIP一覧
- `network check-ip` — グローバルIPv4使用状況チェック（VM割当・DNAT・未使用を表示）
- `network dnat list` / `add` / `edit` / `delete` — DNAT管理（全て対話式）
- `network acl list` / `add` / `edit` / `delete` — ACL管理（全て対話式）

### テンプレート
- `template list` — テンプレート一覧（OS・GPU・ディスク・ユーザー名表示）
- `template show` — テンプレート詳細（全フィールド表示）

### タスク
- `task list` — 操作履歴一覧（件数指定・種別フィルタ対応）
- `task status` / `task wait` — タスク状態確認・完了待機

### UX
- 全テキスト入力で矢印キー対応（questionary）
- API取得中のスピナー表示（ページネーション進捗付き）
- `--json` フラグでJSON出力（全コマンド対応）
- `--verbose` / `-v` でAPIリクエスト/レスポンスの詳細ログ
- Ctrl+C で綺麗に終了（"Aborted."）
- シェル補完対応（`--install-completion`）

### セキュリティ
- クレデンシャルは keyring（macOS Keychain 等）に保存
- Fernet フォールバック（ランダムソルト + PBKDF2）
- トークン・設定ファイルのパーミッション 0o600

### インフラ
- Python 3.13+ / uv
- 140テスト（pytest）
- 並列API取得（httpx.AsyncClient、最大50並列）
