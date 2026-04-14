日本語で回答してください。
t-wadaのTDDを実践してください。

## プロジェクト概要

MDX 1 クラウドインフラのCLIツール。Shibboleth SSO経由でログインし、VM・ネットワーク・テンプレート等をコマンドラインから操作する。

## 技術スタック

- Python 3.13+, uv, Typer, httpx, Pydantic v2, pydantic-settings, Rich, questionary, beautifulsoup4, keyring, cryptography
- テスト: pytest, pytest-mock, respx

## アーキテクチャ

```
commands/  → CLI層（ユーザー対話）
api/       → HTTP通信層（httpxクライアント、エンドポイント、スピナー、ページネーション）
models/    → Pydanticモデル（APIレスポンス）
output/    → 出力フォーマット（Richテーブル / JSON）
credentials/ → クレデンシャル管理（keyring + Fernet）
```

## UI設計パターン

### テキスト入力: questionary.text()
全てのテキスト入力に `questionary.text()` を使う。矢印キーでカーソル移動、Home/End、編集が可能。`typer.prompt()` は使わない。

```python
value = questionary.text("ラベル:", default="デフォルト値").ask()
```

### パスワード入力: questionary.password()
```python
password = questionary.password("パスワード:").ask()
```

### リスト選択: Rich表示 + questionary.text() で番号入力
情報量が多いリスト（テンプレート、プロジェクト等）はRichで色付き表示し、番号で選択する。`questionary.select()` は色やフォーマットが使えないため使わない。

```python
console.print("\n[bold]テンプレート:[/bold]")
for i, t in enumerate(items, 1):
    console.print(f"  {i}) {t.name} [cyan]{t.detail}[/cyan]")
idx = int(questionary.text("番号を入力:").ask()) - 1
selected = items[idx]
```

### 2択選択: questionary.select()
選択肢が2-3個で説明が短い場合のみ `questionary.select()` を使う（矢印キーで選択）。

```python
from questionary import Choice
value = questionary.select("ラベル:", choices=[
    Choice("spot（低価格・中断あり）", value="spot"),
    Choice("guarantee（高価格・中断なし）", value="guarantee"),
]).ask()
```

### 確認ダイアログ: questionary.confirm()
```python
if not questionary.confirm("実行しますか？").ask():
    raise typer.Abort()
```

## API通信パターン

### スピナー: RequestSpinner（自動）
`create_client(silent=False)` で作成したクライアントは、全リクエストで自動的にスピナーが表示される。`--json` 時は `silent=True` で非表示。結果表示前に `stop_active_spinner()` で停止。

```python
client = _get_client(silent=json)  # --json 時はスピナー非表示
data = list_vms(client, pid)
render(data, VM_COLUMNS, json_mode=json)  # render() 内で自動停止
```

render() を使わないコマンド（vm stop 等）では明示的に停止:
```python
power_off_vm(client, vm_id)
stop_active_spinner()
console.print(f"VM {vm_id} を停止しました")
```

### ページネーション: fetch_all()
リスト系APIは `fetch_all()` を使う。サーバーのpage_size上限（100）に対応して自動で全ページ取得。

```python
from mdx_cli.api.pagination import fetch_all
items = fetch_all(client, f"/api/vm/project/{pid}/")
```

### Pydanticモデル: extra="allow"
APIレスポンスのフィールドは推測を含むため、全モデルに `extra="allow"` を設定。未知フィールドでクラッシュしない。

```python
class VM(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str
    status: str
```

### プロジェクトID: resolve_project_id()
`--project-id` はオプショナル。省略時は `mdx project select` で保存済みのIDを使う。

```python
from mdx_cli.commands._common import resolve_project_id
pid = resolve_project_id(project_id)  # 引数 > 保存済み > エラー
```

### 出力: render() でテーブル/JSON切替
```python
render(data, VM_COLUMNS, json_mode=json)  # --json ならJSON、なければRichテーブル
```

テーブルカラムは `output/tables.py` に定義。`model_extra` のフィールドも表示可能。

## VM名パターン

`_name_pattern.py` でバッチ作成用の名前展開:
- `my-vm-{0-9}` → 10台
- `crawler-{a-c}-{0-9}` → 30台
- `node-{00-05}` → ゼロ埋め6台

## 認証

- SSO: `/Shibboleth.sso/Login?target=.../api/sso_login` → IdP（mdxidm.mdx.jp）→ SAML → JWT
- IdPフロー: LSチェック → username/password → TOTP → 属性同意 → SAMLResponse → JWT
- トークン期限切れ: 自動refresh → 失敗時は保存済みID/PWで再ログイン（OTPだけプロンプト）
- `auth logout` で全クレデンシャル削除

## テスト

- questionary の入力はモックする（パイプ入力非対応）
- API呼び出しは respx でモック
- `extra="allow"` のため、テストのAPIレスポンスは実際の形式に合わせる
