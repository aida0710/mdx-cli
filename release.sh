#!/usr/bin/env sh
set -eu

REPO="${MDX_RELEASE_REPO:-aida0710/mdx-cli}"

say() { printf '%s\n' "$*"; }
die() { printf 'release: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: ./release.sh [--dry-run] [--yes] <version>

Examples:
  ./release.sh --dry-run 2.2.0
  ./release.sh 2.2.0

Options:
  --dry-run  事前条件とversionだけ検証し、ファイル・Git・GitHubを変更しない
  --yes      公開前の確認を省略する
EOF
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "$1 が見つかりません"
}

is_stable_semver() {
  printf '%s\n' "$1" | awk -F. '
    NF != 3 { exit 1 }
    $1 !~ /^(0|[1-9][0-9]*)$/ { exit 1 }
    $2 !~ /^(0|[1-9][0-9]*)$/ { exit 1 }
    $3 !~ /^(0|[1-9][0-9]*)$/ { exit 1 }
  '
}

version_gt() {
  awk -v candidate="$1" -v baseline="$2" 'BEGIN {
    split(candidate, a, ".")
    split(baseline, b, ".")
    for (i = 1; i <= 3; i++) {
      if (a[i] + 0 > b[i] + 0) exit 0
      if (a[i] + 0 < b[i] + 0) exit 1
    }
    exit 1
  }'
}

project_version() {
  awk -F'"' '/^version = "/ { print $2; exit }' pyproject.toml
}

module_version() {
  awk -F'"' '/^__version__ = "/ { print $2; exit }' src/mdx_cli/__init__.py
}

lock_version() {
  awk -F'"' '
    $0 == "name = \"mdx-cli\"" { package = 1; next }
    package && /^version = "/ { print $2; exit }
  ' uv.lock
}

assert_version_sync() {
  expected="$1"
  actual_project=$(project_version)
  actual_module=$(module_version)
  actual_lock=$(lock_version)
  [ "$actual_project" = "$expected" ] || die "pyproject.tomlは$actual_projectです（期待: $expected）"
  [ "$actual_module" = "$expected" ] || die "__version__は$actual_moduleです（期待: $expected）"
  [ "$actual_lock" = "$expected" ] || die "uv.lockは$actual_lockです（期待: $expected）"
}

wait_for_run() {
  workflow="$1"
  sha="$2"
  label="$3"
  branch="$4"
  run_id=""
  count=0
  while [ "$count" -lt 60 ]; do
    run_id=$(gh run list \
      --repo "$REPO" \
      --workflow "$workflow" \
      --commit "$sha" \
      --branch "$branch" \
      --event push \
      --limit 10 \
      --json databaseId,createdAt \
      --jq 'sort_by(.createdAt) | last | .databaseId // empty' \
      2>/dev/null || true)
    [ -n "$run_id" ] && break
    count=$((count + 1))
    sleep 2
  done
  [ -n "$run_id" ] || die "$labelのGitHub Actions runを120秒以内に確認できませんでした"
  say "release: $labelを監視します: https://github.com/$REPO/actions/runs/$run_id"
  gh run watch "$run_id" --repo "$REPO" --exit-status --interval 10
}

dry_run=0
assume_yes=0
version=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1 ;;
    --yes) assume_yes=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) die "不明なオプションです: $1" ;;
    *)
      [ -z "$version" ] || die "versionは1つだけ指定してください"
      version=${1#v}
      ;;
  esac
  shift
done

[ -n "$version" ] || { usage >&2; exit 2; }
is_stable_semver "$version" || die "versionは安定版SemVer（例: 2.2.0）で指定してください"
tag="v$version"

need git
need uv

[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$(pwd -P)" ] \
  || die "リポジトリrootで実行してください"
[ "$(git branch --show-current)" = "main" ] || die "main branchで実行してください"

say "release: originとタグを更新します"
git fetch --quiet --prune origin
git fetch --quiet --tags origin

[ -z "$(git status --porcelain)" ] || die "worktreeがcleanではありません"
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] \
  || die "mainとorigin/mainが同期していません"

current=$(project_version)
is_stable_semver "$current" || die "現在のproject versionがSemVerではありません: $current"
assert_version_sync "$current"

latest_tag=$(git tag --list 'v*' --sort=-version:refname \
  | awk '/^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/ { print; exit }')
[ -n "$latest_tag" ] || die "比較対象となる安定版タグがありません"
latest=${latest_tag#v}
[ "$current" = "$latest" ] \
  || die "project version $currentと最新タグ$latest_tagが一致していません"
version_gt "$version" "$latest" \
  || die "$tagは最新タグ$latest_tagより大きくなければなりません"

if git show-ref --verify --quiet "refs/tags/$tag"; then
  die "$tagはすでに存在します"
fi

say "release: 事前条件OK（$latest_tag → $tag）"
if [ "$dry_run" -eq 1 ]; then
  say "release: dry-runのため変更せず終了します"
  exit 0
fi

need gh
gh auth status --hostname github.com >/dev/null 2>&1 \
  || die "GitHub CLIでgithub.comへログインしてください"

if [ "$assume_yes" -ne 1 ]; then
  [ -t 0 ] || die "非対話実行では--yesを指定してください"
  printf '%s' "release: $tagを公開しますか？ [y/N] "
  read -r answer
  case "$answer" in y|Y|yes|YES) ;; *) die "中止しました" ;; esac
fi

say "release: versionを$versionへ更新します"
uv version --no-sync "$version"
version_tmp=$(mktemp "${TMPDIR:-/tmp}/mdx-cli-version.XXXXXX")
awk -v version="$version" '
  /^__version__ = "/ { print "__version__ = \"" version "\""; replaced++; next }
  { print }
  END { if (replaced != 1) exit 1 }
' src/mdx_cli/__init__.py > "$version_tmp" \
  || die "src/mdx_cli/__init__.pyのversion更新に失敗しました"
mv "$version_tmp" src/mdx_cli/__init__.py
assert_version_sync "$version"

say "release: testとlintを実行します"
uv lock --check
uv run --no-sync pytest -q
uv run --no-sync ruff check .
sh -n install.sh agent-skill-install.sh release.sh
git diff --check

unexpected=$(git status --porcelain | awk '{ print $2 }' \
  | awk '$0 != "pyproject.toml" && $0 != "src/mdx_cli/__init__.py" && $0 != "uv.lock"')
[ -z "$unexpected" ] || die "version更新以外の変更を検出しました:\n$unexpected"

git add pyproject.toml src/mdx_cli/__init__.py uv.lock
git commit \
  -m "chore(release): $tagを準備" \
  -m "$tagのversion情報を揃え、公開前検証を完了する。"
release_commit=$(git rev-parse HEAD)
git push origin main
wait_for_run test.yml "$release_commit" "main CI" main

git tag -a "$tag" \
  -m "mdx-cli $tag" \
  -m "$tagを公開する。"
git push origin "$tag"
wait_for_run release.yml "$release_commit" "Release CI" "$tag"

assets=$(gh release view "$tag" --repo "$REPO" --json assets --jq '.assets[].name')
for asset in \
  checksums.txt install.sh install.ps1 \
  mdx-darwin-arm64 mdx-linux-x86_64 mdx-linux-arm64 mdx-windows-x86_64.exe
do
  printf '%s\n' "$assets" | grep -Fx "$asset" >/dev/null \
    || die "GitHub Releaseに$assetがありません"
done
release_url=$(gh release view "$tag" --repo "$REPO" --json url --jq '.url')
say "release: 公開完了 $release_url"
