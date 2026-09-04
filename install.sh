#!/usr/bin/env sh
# mdx-cli の実行ファイルを入れる。
#
#   curl -fsSL https://github.com/aida0710/mdx-cli/releases/latest/download/install.sh | sh
#
# 何をするかは標準出力に出す:
#   1. OS とアーキテクチャに対応する成果物の選択
#   2. checksums.txt による SHA-256 の照合
#   3. 置き先の決定と既存ファイルの置換
#   4. PATH の確認と、先に解決される別の mdx の検出
#
# 環境変数:
#   MDX_VERSION      入れる版（既定: 最新リリース。例: v2.0.0）
#   MDX_INSTALL_DIR  置き先（既定: root なら /usr/local/bin、他は ~/.local/bin）

set -eu

REPO="${MDX_REPO:-aida0710/mdx-cli}"

say() { printf '%s\n' "$*"; }
note() { printf '  %s\n' "$*"; }
die() { printf 'mdx: %s\n' "$*" >&2; exit 1; }

if command -v curl >/dev/null 2>&1; then
  fetch() { curl -fsSL --connect-timeout 10 --max-time 300 "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
  fetch() { wget -q -T 30 -t 3 -O "$2" "$1"; }
else
  die "curl も wget も見つかりません"
fi

# ── 成果物を選ぶ ──────────────────────────────────────────────
# 配布していない組み合わせでは代替を推測せず、ソースからの導入を案内して終了する。
os=$(uname -s)
arch=$(uname -m)
case "$os" in
  Darwin) plat=darwin ;;
  Linux) plat=linux ;;
  *) die "$os 向けのバイナリは配布していません（Windows は install.ps1 を使ってください）" ;;
esac
case "$plat:$arch" in
  darwin:arm64 | darwin:aarch64) asset="mdx-darwin-arm64" ;;
  linux:x86_64 | linux:amd64) asset="mdx-linux-x86_64" ;;
  linux:aarch64 | linux:arm64) asset="mdx-linux-arm64" ;;
  *) die "$os $arch 向けのバイナリは配布していません。uv tool install で導入してください" ;;
esac

if [ -n "${MDX_VERSION:-}" ]; then
  tag="$MDX_VERSION"
  case "$tag" in v*) ;; *) tag="v$tag" ;; esac
  base="https://github.com/$REPO/releases/download/$tag"
else
  tag="latest"
  base="https://github.com/$REPO/releases/latest/download"
fi
say "mdx: $asset ($tag) を入れます"

# uv tool の entrypoint を上書きすると、uv 側の登録だけが残り、後日の
# `uv tool uninstall` がこのバイナリを削除する。先に正規の移行を要求する。
if command -v uv >/dev/null 2>&1; then
  uv_tool_dir=$(uv tool dir 2>/dev/null || true)
  if [ -n "$uv_tool_dir" ] && [ -f "$uv_tool_dir/mdx-cli/uv-receipt.toml" ]; then
    die "uv tool 版の mdx-cli が登録されています。先に 'uv tool uninstall mdx-cli' を実行してください"
  fi
fi

# ── 置き先を決める ────────────────────────────────────────────
# 非 root では sudo を要求せず、ホーム配下だけを触る。
if [ -n "${MDX_INSTALL_DIR:-}" ]; then
  dir="$MDX_INSTALL_DIR"
  why="MDX_INSTALL_DIR"
elif [ "$(id -u)" = "0" ]; then
  dir="/usr/local/bin"
  why="root で実行しているため"
else
  dir="$HOME/.local/bin"
  why="root ではないため、ホーム配下のみ変更"
fi
note "置き先: $dir/mdx（${why}）"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

# ── SHA-256 を照合する ────────────────────────────────────────
if command -v sha256sum >/dev/null 2>&1; then
  sum() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then
  sum() { shasum -a 256 "$1" | cut -d' ' -f1; }
else
  die "SHA-256 を計算する sha256sum または shasum が見つかりません"
fi

fetch "$base/checksums.txt" "$tmp/checksums.txt" 2>/dev/null \
  || die "checksums.txt を取得できないため中止しました: $base/checksums.txt"
expected_lines=$(awk -v a="$asset" '$2 == a || $2 == "*"a {print $1}' "$tmp/checksums.txt")
expected_count=$(printf '%s\n' "$expected_lines" | awk 'NF {count++} END {print count + 0}')
[ "$expected_count" = "1" ] || die "checksums.txt の $asset は1行である必要があります（実際: ${expected_count}行）"
expected=$(printf '%s' "$expected_lines" | tr 'A-F' 'a-f')
[ "${#expected}" = "64" ] || die "checksums.txt の SHA-256 形式が不正です"
case "$expected" in *[!0-9a-f]*) die "checksums.txt の SHA-256 形式が不正です" ;; esac

fetch "$base/$asset" "$tmp/mdx" || die "ダウンロードに失敗しました: $base/$asset"
actual=$(sum "$tmp/mdx" | tr 'A-F' 'a-f') || die "SHA-256 の計算に失敗しました"
[ "$expected" = "$actual" ] || die "SHA-256 が一致しません（期待 $expected / 実際 ${actual}）"
note "SHA-256 一致: $actual"

# ── 置く ──────────────────────────────────────────────────────
mkdir -p "$dir" || die "$dir を作成できません"
chmod 0755 "$tmp/mdx"
# 実行中バイナリの上書きを避けるため、同ディレクトリに置いてから rename する
mv "$tmp/mdx" "$dir/mdx.new" || die "$dir に書き込めません（MDX_INSTALL_DIR で別の場所を指定できます）"
mv "$dir/mdx.new" "$dir/mdx"
say "mdx: $dir/mdx を更新しました"

# ── 使える状態か確かめる ──────────────────────────────────────
case ":${PATH:-}:" in
  *":$dir:"*) ;;
  *) note "$dir は PATH にありません。シェルの設定に export PATH=\"$dir:\$PATH\" を追加してください" ;;
esac

existing=$(command -v mdx 2>/dev/null || true)
if [ -n "$existing" ] && [ "$existing" != "$dir/mdx" ]; then
  note "PATH 上では $existing が先に解決されます"
fi

if version=$("$dir/mdx" --version 2>/dev/null); then
  say "mdx: バージョン $version"
else
  note "$dir/mdx --version を実行できませんでした（macOS では初回に許可が必要な場合があります）"
fi
