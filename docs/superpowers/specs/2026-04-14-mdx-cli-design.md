# MDX 1 CLI ツール 設計仕様書

## 概要

MDX 1 クラウドインフラプラットフォームの全APIをコマンドラインから操作するCLIツール。VM管理、プロジェクト情報確認、ネットワーク管理、スクリプト連携を主な用途とする。

## 技術スタック

- **言語**: Python 3.13+
- **パッケージマネージャ**: uv
- **CLIフレームワーク**: Typer（型ヒント駆動）
- **HTTPクライアント**: httpx
- **データモデル**: Pydantic v2
- **設定管理**: pydantic-settings
- **ターミナルUI**: Rich（typer[all]に同梱）
- **クレデンシャル保存**: keyring + cryptography（Fernetフォールバック）
- **テスト**: pytest（t-wada TDD方式）

## プロジェクト構造

```
mdx-cli/
  pyproject.toml
  src/
    mdx_cli/
      __init__.py
      main.py                  # Typerルートアプリ、グローバルオプション
      commands/
        __init__.py
        auth.py                # login, logout, status
        project.py             # list, show, storage, keys
        vm.py                  # list, show, deploy, start, stop, destroy, sync
        network.py             # segment list/show, acl list, dnat list
        template.py            # list
        task.py                # status, wait
      api/
        __init__.py
        client.py              # httpxクライアントラッパー
        auth.py                # JWT認証フロー（httpx.Auth サブクラス）
        endpoints/
          __init__.py
          projects.py          # Pydanticモデルを返すAPI呼び出し
          vms.py
          networks.py
          tasks.py
      models/
        __init__.py
        project.py             # Pydantic BaseModelクラス
        vm.py
        network.py
        task.py
        auth.py                # TokenPairモデル
        enums.py               # VMStatus, TaskStatus, ServiceLevel等
      credentials/
        __init__.py
        store.py               # keyring + Fernet暗号化フォールバック
      output/
        __init__.py
        formatting.py          # model_dump_json() / Richテーブル切替
        tables.py              # モデルごとのカラム定義
      settings.py              # pydantic-settings設定クラス
  tests/
    __init__.py
    conftest.py
    test_models/
    test_api/
    test_commands/
    test_credentials/
    test_output/
```

## 依存パッケージ

```toml
dependencies = [
    "typer[all]>=0.12",
    "httpx>=0.27",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "keyring>=25.0",
    "cryptography>=42.0",
]

[project.scripts]
mdx = "mdx_cli.main:app"
```

## 認証設計

### ベースURL

`https://oprpl.mdx.jp`

### 認証フロー

```
初回ログイン（mdx auth login）:
  1. ユーザー名入力 → keyringに保存
  2. パスワード入力 → keyringに保存
  3. OTP入力（毎回プロンプト、保存しない）
  4. MDX認証基盤トークン取得（ログインAPIへPOST）
  5. POST /api/auth/ {token: <MDX認証基盤トークン>} → JWT取得
  6. JWT を ~/.config/mdx-cli/token.json に保存

通常の操作:
  1. 保存済みJWTを Authorization: JWT <token> ヘッダーに付与
  2. JWT期限切れ → POST /api/refresh/ {token: <JWT>} で自動更新
  3. refresh失敗 → keyringからID/PW取得 + OTPプロンプト → 再ログイン

注意: ログインAPIの詳細（MDX認証基盤トークン取得部分）は未調査。
      実装時にブラウザのDevToolsで実際のリクエストをキャプチャして確認が必要。
```

### httpx.Auth サブクラス

```python
class MDXAuth(httpx.Auth):
    """全APIリクエストに透過的にJWT認証を注入する"""
    
    def auth_flow(self, request):
        # 1. 保存済みJWTがあればヘッダーに付与
        # 2. 401応答 → refreshを試行
        # 3. refresh失敗 → OTPプロンプト → 再ログイン
        # 4. コマンド側は認証を意識しない
```

### クレデンシャル保存

- **主経路**: keyringライブラリ（macOS Keychain）
  - サービス名: `mdx-cli`
  - 保存項目: username, password
- **フォールバック**: `~/.config/mdx-cli/credentials.enc` にFernet暗号化で保存
  - ヘッドレス環境（keyringデーモンなし）向け
  - マシン固有のキー導出
- **OTP**: 保存しない。ワンタイムパスワードなので毎回対話的にプロンプト
- **JWT**: `~/.config/mdx-cli/token.json` に平文保存（短命トークンのため）

## コマンド一覧

### 認証

| コマンド | 説明 |
|---------|------|
| `mdx auth login` | ログイン（ID/PW/OTP入力） |
| `mdx auth logout` | トークン・クレデンシャル削除 |
| `mdx auth status` | 認証状態確認 |

### プロジェクト

| コマンド | API | 説明 |
|---------|-----|------|
| `mdx project list` | GET /api/project/assigned/ | アサイン済みプロジェクト一覧 |
| `mdx project show <id>` | GET /api/project/{id}/summary/ | プロジェクトサマリー |
| `mdx project storage <id>` | GET /api/project/{id}/storage/ | ストレージ情報 |
| `mdx project keys <id>` | GET /api/project/{id}/access_key/ | アクセスキー一覧 |

### 仮想マシン

| コマンド | API | 説明 |
|---------|-----|------|
| `mdx vm list` | GET /api/vm/project/{id}/ | VM一覧 |
| `mdx vm show <id>` | GET /api/vm/{id}/ | VM詳細 |
| `mdx vm deploy` | POST /api/vm/deploy/ | VMデプロイ（対話的パラメータ入力） |
| `mdx vm start <id>` | POST /api/vm/{id}/power_on/ | 起動（--service-level spot\|guarantee） |
| `mdx vm stop <id>` | POST /api/vm/{id}/power_off/ | 強制停止 |
| `mdx vm destroy <id>` | POST /api/vm/{id}/destroy/ | 削除 |
| `mdx vm sync` | POST /api/vm/synchronize/project/{id}/ | VM情報同期 |

### テンプレート

| コマンド | API | 説明 |
|---------|-----|------|
| `mdx template list` | GET /api/catalog/project/{id}/ | テンプレート一覧 |

### ネットワーク

| コマンド | API | 説明 |
|---------|-----|------|
| `mdx network segment list` | GET /api/segment/project/{id}/all/ | セグメント一覧 |
| `mdx network segment show <id>` | GET /api/segment/{id}/summary/ | セグメントサマリー |
| `mdx network acl list <segment_id>` | GET /api/acl/segment/{id}/ | ACL一覧 |
| `mdx network dnat list` | GET /api/dnat/project/{id}/ | DNAT一覧 |

### タスク

| コマンド | API | 説明 |
|---------|-----|------|
| `mdx task status <id>` | GET /api/task/{id}/ | タスク状態確認 |
| `mdx task wait <id>` | GET /api/task/{id}/ (ポーリング) | タスク完了まで待機 |

### グローバルオプション

| オプション | 環境変数 | 説明 |
|-----------|---------|------|
| `--json` | - | JSON出力モード |
| `--project-id` / `-p` | `MDX_PROJECT_ID` | デフォルトプロジェクトID |

## Pydanticモデル設計

### 列挙型（enums.py）

```python
class VMStatus(str, Enum):
    RUNNING = "Running"
    STOPPED = "Stopped"
    DEPLOYING = "Deploying"
    DESTROYING = "Destroying"

class ServiceLevel(str, Enum):
    SPOT = "spot"
    GUARANTEE = "guarantee"

class TaskStatus(str, Enum):
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
```

### VMモデル（vm.py）

```python
class VM(BaseModel):
    uuid: str
    name: str
    status: VMStatus
    project: str
    pack_type: str
    pack_num: int
    service_level: ServiceLevel

class VMDeployRequest(BaseModel):
    catalog: str
    project: str
    vm_name: str
    disk_size: int = 40
    storage_network: str = "portgroup"
    pack_type: str = "cpu"
    pack_num: int = 3
    service_level: ServiceLevel = ServiceLevel.SPOT
    network_adapters: list[dict]
    shared_key: str
    power_on: bool = False
    os_type: str = "Linux"
    template_name: str
    nvlink: bool = False

class VMDeployResponse(BaseModel):
    task_id: list[str]
```

### タスクモデル（task.py）

```python
class Task(BaseModel):
    uuid: str
    type: str
    object_uuid: str
    object_name: str
    start_datetime: str
    end_datetime: str | None
    status: TaskStatus
    progress: int

    @computed_field
    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
```

### 認証モデル（auth.py）

```python
class TokenPair(BaseModel):
    token: str
    expires_at: datetime | None = None
```

## 出力フォーマット設計

### デフォルト: Richテーブル

```python
# output/tables.py
VM_COLUMNS = [
    ("UUID", "uuid"),
    ("名前", "name"),
    ("状態", "status"),
    ("パック数", "pack_num"),
    ("サービスレベル", "service_level"),
]
```

### JSON出力（--json）

`model.model_dump_json(indent=2)` または `[m.model_dump() for m in models]` をJSON出力。
スクリプト連携やjqでのパイプ処理に対応。

### 出力切替ロジック（formatting.py）

```python
def render(data: BaseModel | list[BaseModel], columns: list[tuple], json_mode: bool):
    if json_mode:
        # model_dump_json()
    else:
        # Rich table
```

## タスクポーリング設計

- deploy/destroy 後に自動でポーリング開始
- `rich.progress` でプログレスバー表示（API側のprogress値を利用）
- `--no-wait` フラグでタスクIDだけ返してスキップ可能
- `mdx task wait <id>` で個別にポーリングも可能
- ポーリング間隔: 3秒（設定可能）
- タイムアウト: 600秒（設定可能）

## 設定管理

```python
# settings.py
class Settings(BaseSettings):
    base_url: str = "https://oprpl.mdx.jp"
    default_project_id: str | None = None
    request_timeout: int = 30
    task_poll_interval: int = 3
    task_poll_timeout: int = 600
    config_dir: Path = Path("~/.config/mdx-cli").expanduser()

    model_config = SettingsConfigDict(
        env_prefix="MDX_",
        toml_file="~/.config/mdx-cli/config.toml",
    )
```

- 環境変数: `MDX_BASE_URL`, `MDX_DEFAULT_PROJECT_ID`, `MDX_REQUEST_TIMEOUT` 等
- 設定ファイル: `~/.config/mdx-cli/config.toml`
- コマンドラインオプション > 環境変数 > 設定ファイル > デフォルト値

## 未解決事項

1. **ログインAPIの詳細**: MDX認証基盤トークン取得のAPIエンドポイントとリクエスト形式が未調査。実装時にブラウザDevToolsでキャプチャが必要。
2. **グローバルIP管理API**: IP割当・DNAT作成/削除のAPIが未発見。現時点は一覧取得のみ実装し、後からCRUD追加。
3. **APIレスポンスの正確なフィールド**: Pydanticモデルのフィールドは推測を含む。実際のAPI応答を見てモデルを調整する必要がある。

## テスト方針

t-wada TDD方式で開発する:
1. レッド: 失敗するテストを先に書く
2. グリーン: テストを通す最小限のコードを書く
3. リファクタ: コードを改善する

テスト対象:
- **モデル層**: Pydanticモデルのバリデーション・シリアライゼーション
- **API層**: httpxのモックを使ったエンドポイント関数テスト
- **クレデンシャル層**: keyring/Fernetの保存・取得テスト
- **出力層**: テーブル/JSON出力のフォーマットテスト
- **コマンド層**: Typerのテストクライアントを使った統合テスト
