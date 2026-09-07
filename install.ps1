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
    $bundle = $false
    if (Get-Content "$tmp\checksums.txt" | Where-Object { $_ -match '\s\*?mdx-windows-x86_64\.zip$' }) {
        $asset = 'mdx-windows-x86_64.zip'
        $bundle = $true
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

    $source = "$tmp\mdx.exe"
    if ($bundle) {
        # 展開前に、全エントリが mdx/ 配下に収まることを確認する。
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead((Get-Item -LiteralPath $source).FullName)
        try {
            foreach ($entry in $zip.Entries) {
                $name = $entry.FullName.Replace('\', '/')
                if ($name -notmatch '^mdx/' -or $name -match '(^|/)\.\.(/|$)' -or $name.Contains(':')) {
                    throw 'mdx: アーカイブ内のパスが不正です'
                }
            }
        } finally { $zip.Dispose() }
        [IO.Compression.ZipFile]::ExtractToDirectory((Get-Item -LiteralPath $source).FullName, (Join-Path $tmp 'unpacked'))
        $source = "$tmp\unpacked\mdx\mdx.exe"
        if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
            -not (Test-Path -LiteralPath "$tmp\unpacked\mdx\_internal" -PathType Container)) {
            throw 'mdx: 実行ファイルまたは _internal がありません'
        }
    }

    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $lockPath = Join-Path $dir '.mdx-install.lock'
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $backup = Join-Path $dir ('.mdx-backup-' + [guid]::NewGuid())
    $internal = Join-Path $dir '_internal'
    $stage = Join-Path $dir ('.mdx-stage-' + [guid]::NewGuid())
    $hasBinary = $false
    $hasInternal = $false
    $newBinary = $false
    $newInternal = $false
    $keepBackup = $false
    try {
        New-Item -ItemType Directory -Path $stage | Out-Null
        Copy-Item -LiteralPath $source -Destination (Join-Path $stage 'mdx.exe')
        if ($bundle) {
            Copy-Item -LiteralPath "$tmp\unpacked\mdx\_internal" -Destination (Join-Path $stage '_internal') -Recurse
        }
        $source = Join-Path $stage 'mdx.exe'
        New-Item -ItemType Directory -Path $backup | Out-Null
        # 実行中ファイルがロックされていれば、runtimeを触る前に失敗する。
        if (Test-Path -LiteralPath $target) {
            Move-Item -Force $target (Join-Path $backup 'mdx.exe')
            $hasBinary = $true
        }
        if ($bundle) {
            if (Test-Path -LiteralPath $internal) {
                Move-Item -Force $internal (Join-Path $backup '_internal')
                $hasInternal = $true
            }
            Move-Item -Force (Join-Path $stage '_internal') $internal
            $newInternal = $true
        }
        Move-Item -Force $source $target
        $newBinary = $true
        $installedVersion = & $target --version
        if ($LASTEXITCODE -ne 0) { throw 'mdx: 新版を起動できません' }
    } catch {
        $installError = $_
        try {
            if ($newBinary) { Remove-Item -LiteralPath $target -Force }
            if ($newInternal) { Remove-Item -LiteralPath $internal -Recurse -Force }
            if ($hasInternal) { Move-Item -Force (Join-Path $backup '_internal') $internal }
            if ($hasBinary) { Move-Item -Force (Join-Path $backup 'mdx.exe') $target }
        } catch {
            $keepBackup = $true
            throw "mdx: 復元に失敗しました。旧版は $backup に保存しています。$($_.Exception.Message)"
        }
        throw $installError
    } finally {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        $lock.Dispose()
        Remove-Item -LiteralPath $lockPath -Force
        if (-not $keepBackup) { Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue }
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

Write-Host ("mdx: バージョン " + $installedVersion)
