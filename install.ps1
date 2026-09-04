# mdx-cli の実行ファイルを入れる。
#
#   powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/aida0710/mdx-cli/releases/latest/download/install.ps1 | iex"
#
# 環境変数:
#   MDX_VERSION      入れる版（既定: 最新リリース。例: v2.0.0）
#   MDX_INSTALL_DIR  置き先（既定: %LOCALAPPDATA%\Programs\mdx）

$ErrorActionPreference = 'Stop'

$repo = if ($env:MDX_REPO) { $env:MDX_REPO } else { 'aida0710/mdx-cli' }
$asset = 'mdx-windows-x86_64.exe'

function Note($m) { Write-Host "  $m" }

if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    Note 'ARM64 Windows では x64 バイナリをエミュレーションで実行します'
}

if ($env:MDX_VERSION) {
    $tag = $env:MDX_VERSION
    if (-not $tag.StartsWith('v')) { $tag = "v$tag" }
    $base = "https://github.com/$repo/releases/download/$tag"
} else {
    $tag = 'latest'
    $base = "https://github.com/$repo/releases/latest/download"
}
Write-Host "mdx: $asset ($tag) を入れます"

# uv の entrypoint を残したまま別バイナリを入れると、PATH競合や後日の削除が起きる。
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    $uvToolDir = (& $uv.Source tool dir 2>$null | Select-Object -First 1)
    if ($uvToolDir -and (Test-Path (Join-Path $uvToolDir 'mdx-cli\uv-receipt.toml'))) {
        throw "mdx: uv tool 版の mdx-cli が登録されています。先に 'uv tool uninstall mdx-cli' を実行してください"
    }
}

$dir = if ($env:MDX_INSTALL_DIR) { $env:MDX_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'Programs\mdx' }
$target = Join-Path $dir 'mdx.exe'
Note "置き先: $target"

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("mdx-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    # checksums.txt を検証できない場合は、バイナリを配置も実行もしない。
    try {
        Invoke-WebRequest -Uri "$base/checksums.txt" -OutFile "$tmp\checksums.txt" -UseBasicParsing
    } catch {
        throw "mdx: checksums.txt を取得できないため中止しました: $base/checksums.txt`n$($_.Exception.Message)"
    }
    $pattern = "\s\*?" + [regex]::Escape($asset) + "$"
    $lines = @(Get-Content "$tmp\checksums.txt" | Where-Object { $_ -match $pattern })
    if ($lines.Count -ne 1) {
        throw "mdx: checksums.txt の $asset は1行である必要があります（実際: $($lines.Count)行）"
    }
    $expected = ($lines[0] -split '\s+')[0].ToLower()
    if ($expected -notmatch '^[0-9a-f]{64}$') {
        throw 'mdx: checksums.txt の SHA-256 形式が不正です'
    }

    Invoke-WebRequest -Uri "$base/$asset" -OutFile "$tmp\mdx.exe" -UseBasicParsing
    $actual = (Get-FileHash "$tmp\mdx.exe" -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) {
        throw "mdx: SHA-256 が一致しません（期待 $expected / 実際 $($actual)）"
    }
    Note "SHA-256 一致: $actual"

    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    # 置き換えに失敗した場合は、退避した既存バイナリを必ず元へ戻す。
    $backup = "$target.old"
    $hasBackup = $false
    if (Test-Path $target) {
        Move-Item -Force $target $backup
        $hasBackup = $true
    }
    try {
        Move-Item -Force "$tmp\mdx.exe" $target
    } catch {
        if ($hasBackup -and (Test-Path $backup)) {
            Move-Item -Force $backup $target
        }
        throw
    }
    if ($hasBackup) {
        Remove-Item -Force $backup
    }
    Write-Host "mdx: $target を更新しました"
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

# 置き先をユーザーの PATH に入れる（既にあれば触らない）
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $dir) {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$dir", 'User')
    Note "$dir をユーザーの PATH に追加しました（新しいターミナルから有効）"
}
$env:Path = "$env:Path;$dir"

$existing = (Get-Command mdx -ErrorAction SilentlyContinue).Source
if ($existing -and $existing -ne $target) {
    Note "PATH 上では $existing が先に解決されます"
}

try {
    Write-Host ("mdx: バージョン " + (& $target --version))
} catch {
    Note "$target --version を実行できませんでした"
}
