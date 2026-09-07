# インストール

macOS・Linux・Windows向けの単体バイナリを配布しています。Pythonのインストールは不要です。

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

### uv版からバイナリ版へ切り替える場合

これまで `uv tool install .` で導入していた場合は、uv の実行リンクと単体バイナリが
競合しないよう、先にuv版を削除します。`~/.config/mdx-cli` の設定・認証情報は残ります。

```bash
uv tool uninstall mdx-cli
```

削除後、上記のOS別インストーラを実行してください。インストーラもuv版を検出した場合は
上書きせず、この移行手順を案内して終了します。

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
