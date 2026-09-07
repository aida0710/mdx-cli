# mdx-cli

[MDX 1](https://mdx.jp/) クラウドインフラプラットフォームの非公式CLIツール。

Web ポータル (oprpl.mdx.jp) の操作をコマンドラインから実行できます。VM の一括作成・起動・停止、SSH接続、ネットワーク管理、DNAT/ACL 設定などに対応。

<img width="2606" height="1914" alt="image" src="https://github.com/user-attachments/assets/03419e55-f040-4c11-b0f0-e01125324a76" />

## 前提条件

- `oprpl.mdx.jp` および `mdxidm.mdx.jp` への疎通が必要です。
- ソースから入れる場合のみ Python 3.13+ と [uv](https://docs.astral.sh/uv/)（バイナリは単体で動きます）

## インストール

### uv版からバイナリ版へ切り替える場合

これまで `uv tool install .` で導入していた場合は、uv の実行リンクと単体バイナリが
競合しないよう、先にuv版を削除します。`~/.config/mdx-cli` の設定・認証情報は残ります。

```bash
uv tool uninstall mdx-cli
```

削除後、以下のOS別インストーラを実行してください。インストーラもuv版を検出した場合は
上書きせず、この移行手順を案内して終了します。

### バイナリ（推奨）

macOS / Linux:

```bash
curl -fsSL https://github.com/aida0710/mdx-cli/releases/latest/download/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://github.com/aida0710/mdx-cli/releases/latest/download/install.ps1 | iex
```

- 置き先は root なら `/usr/local/bin`、それ以外は `~/.local/bin`（Windows は `%LOCALAPPDATA%\Programs\mdx`）。`MDX_INSTALL_DIR` で変更できます
- 版を固定する場合は、macOS / Linux では
  `curl -fsSL https://github.com/aida0710/mdx-cli/releases/latest/download/install.sh | MDX_VERSION=v2.1.0 sh`、
  Windows では実行前に `$env:MDX_VERSION = 'v2.1.0'` を設定します
- リリースの `checksums.txt` で SHA-256 を照合し、取得不能・不一致ならインストールしません
- アップデートは同じコマンドの再実行
- 配布しているのは macOS(arm64) / Linux(x86_64, arm64) / Windows(x86_64) です

### ソースから（uv）

```bash
uv tool install .
```

アップデート:

```bash
git pull
uv tool install . --force
```

インストール後の確認:

```bash
mdx --version
```

## Skill としてインストール

Codex / Claude Code の skill として使う場合:

```bash
curl -fsSL https://raw.githubusercontent.com/aida0710/mdx-cli/main/agent-skill-install.sh | sh
```

ローカルのこのリポジトリから入れる場合:

```bash
sh agent-skill-install.sh --source . --codex-only
```

## リリース

リリース担当者はcleanな`main`で、現在より大きい安定版SemVerを指定します。

```bash
./release.sh --dry-run 2.2.0  # 事前条件だけ確認
./release.sh 2.2.0            # 確認後、main CI・タグ・Release CIまで実行
```

同名タグ、現在以下のversion、未commit変更、`origin/main`と同期していない状態では停止します。
非対話実行で確認を省略する場合だけ`--yes`を追加します。

## ドキュメント

インストール後のクイックスタート、認証、VM・ネットワークの操作、設定については、
[mdx-cli ドキュメント](https://aida0710.github.io/mdx-cli/)をご覧ください。
