"""配布インストーラの破壊防止と完全性検証。"""

import os
import hashlib
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\nset -eu\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _base_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uv_tools = tmp_path / "uv-tools"
    uv_tools.mkdir()

    _write_executable(fake_bin / "uname", 'case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; esac\n')
    _write_executable(fake_bin / "id", 'echo 501\n')
    _write_executable(
        fake_bin / "uv",
        'if [ "$1 $2" = "tool dir" ]; then printf "%s\\n" "$FAKE_UV_TOOL_DIR"; exit 0; fi\nexit 1\n',
    )

    env = os.environ.copy()
    env.update(
        {
            "FAKE_UV_TOOL_DIR": str(uv_tools),
            "HOME": str(tmp_path / "home"),
            "MDX_INSTALL_DIR": str(tmp_path / "install"),
            "MDX_VERSION": "v2.0.0",
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        }
    )
    return env, fake_bin


def _run_install_sh(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(ROOT / "install.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_sh_refuses_to_overwrite_uv_managed_mdx(tmp_path):
    env, fake_bin = _base_env(tmp_path)
    receipt = Path(env["FAKE_UV_TOOL_DIR"]) / "mdx-cli" / "uv-receipt.toml"
    receipt.parent.mkdir()
    receipt.write_text("[tool]\n")
    fetch_marker = tmp_path / "fetch-called"
    env["FETCH_MARKER"] = str(fetch_marker)
    _write_executable(fake_bin / "curl", 'touch "$FETCH_MARKER"\nexit 99\n')

    result = _run_install_sh(env)

    assert result.returncode != 0
    assert "uv tool uninstall mdx-cli" in result.stderr
    assert not fetch_marker.exists()


def test_install_sh_does_not_install_without_checksums(tmp_path):
    env, fake_bin = _base_env(tmp_path)
    _write_executable(
        fake_bin / "curl",
        '''
url=""
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
case "$url" in
  */mdx-darwin-arm64)
    printf '%s\\n' '#!/bin/sh' 'echo 2.0.0' > "$out"
    ;;
  */checksums.txt)
    exit 22
    ;;
  *) exit 23 ;;
esac
''',
    )

    result = _run_install_sh(env)

    assert result.returncode != 0
    assert "checksums.txt" in result.stderr
    assert not (Path(env["MDX_INSTALL_DIR"]) / "mdx").exists()


def test_install_sh_verifies_checksum_before_installing(tmp_path):
    env, fake_bin = _base_env(tmp_path)
    binary = b"#!/bin/sh\necho 2.0.0\n"
    env["FAKE_BINARY_HASH"] = hashlib.sha256(binary).hexdigest()
    _write_executable(
        fake_bin / "curl",
        '''
url=""
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
case "$url" in
  */checksums.txt)
    printf '%s  %s\\n' "$FAKE_BINARY_HASH" 'mdx-darwin-arm64' > "$out"
    ;;
  */mdx-darwin-arm64)
    printf '%s\\n' '#!/bin/sh' 'echo 2.0.0' > "$out"
    ;;
  *) exit 23 ;;
esac
''',
    )

    result = _run_install_sh(env)

    assert result.returncode == 0, result.stdout + result.stderr
    installed = Path(env["MDX_INSTALL_DIR"]) / "mdx"
    assert installed.exists()
    assert subprocess.check_output([str(installed)], text=True).strip() == "2.0.0"
    assert "SHA-256 一致" in result.stdout


def test_installers_never_advertise_skipping_checksum_verification():
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / name).read_text()
        assert "照合をスキップ" not in text
        assert "uv tool uninstall mdx-cli" in text


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShellがありません")
@pytest.mark.parametrize("bundle", [False, True])
def test_install_ps1_restores_previous_binary_when_replacement_fails(tmp_path, bundle):
    """新バイナリの配置失敗で、退避した旧版を失わない。"""
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    target = install_dir / "mdx.exe"
    target.write_text("old-binary")
    import zipfile

    internal = install_dir / '_internal'
    internal.mkdir()
    (internal / 'marker').write_text('old-runtime')
    archive = tmp_path / 'bundle.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('mdx/mdx.exe', 'new-binary')
        z.writestr('mdx/_internal/marker', 'new-runtime')
    asset = 'mdx-windows-x86_64.zip' if bundle else 'mdx-windows-x86_64.exe'
    binary_expr = f"[IO.File]::ReadAllBytes('{archive}')" if bundle else "[System.Text.Encoding]::UTF8.GetBytes('new-binary')"
    harness = tmp_path / "rollback-test.ps1"
    harness.write_text(
        fr'''
$ErrorActionPreference = 'Stop'
$env:Path = '/usr/bin:/bin'
$env:UV_TOOL_DIR = '{tmp_path / "empty-uv-tools"}'
$env:MDX_INSTALL_DIR = '{install_dir}'
$env:MDX_VERSION = 'v2.0.0'
$global:replacementFailed = $false
$global:target = '{target}'
$global:newBytes = {binary_expr}
$global:newHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($global:newBytes)).ToLower()

function global:Invoke-WebRequest {{
    param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing)
    if ($Uri.EndsWith('/checksums.txt')) {{
        Set-Content -NoNewline -Path $OutFile -Value "$global:newHash  {asset}"
    }} else {{
        [IO.File]::WriteAllBytes($OutFile.Replace('\', [IO.Path]::DirectorySeparatorChar), $global:newBytes)
    }}
}}

function global:Move-Item {{
    param([string]$Path, [string]$Destination, [switch]$Force)
    if (-not $global:replacementFailed -and $Path.EndsWith('mdx.exe') -and $Destination -eq $global:target) {{
        $global:replacementFailed = $true
        throw 'simulated replacement failure'
    }}
    Microsoft.PowerShell.Management\Move-Item -Path $Path -Destination $Destination -Force:$Force
}}

try {{
    & '{ROOT / "install.ps1"}'
}} catch {{
    if ($global:replacementFailed -and (Test-Path $global:target) -and (Get-Content -Raw $global:target) -eq 'old-binary') {{ exit 0 }}
    Write-Error ('旧バイナリが復元されませんでした: ' + $_)
}}
exit 1
'''
    )

    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(harness)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (internal / "marker").read_text() == "old-runtime"


def test_readme_documents_uv_migration_before_binary_install():
    readme = (ROOT / "README.md").read_text()
    migration = readme.index("uv tool uninstall mdx-cli")
    binary_install = readme.index("curl -fsSL", migration)
    assert migration < binary_install


def _archive_downloads(tmp_path, env, fake_bin, *, broken=False):
    import tarfile

    bundle = tmp_path / 'bundle' / 'mdx'
    (bundle / '_internal').mkdir(parents=True)
    (bundle / '_internal' / 'version').write_text('2.1.1\n')
    _write_executable(bundle / 'mdx', 'exit 9\n' if broken else
                      'cat "$(dirname "$(realpath "$0")")/_internal/version"\n')
    archive = tmp_path / 'release.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(bundle, arcname='mdx')
    env['FAKE_ARCHIVE'] = str(archive)
    env['FAKE_ARCHIVE_HASH'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    _write_executable(fake_bin / 'curl', '''
url=""
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
case "$url" in
  */checksums.txt) printf '%s  mdx-darwin-arm64.tar.gz\\n' "$FAKE_ARCHIVE_HASH" > "$out" ;;
  */mdx-darwin-arm64.tar.gz) cp "$FAKE_ARCHIVE" "$out" ;;
  *) exit 23 ;;
esac
''')


def test_install_sh_installs_runtime_and_updates_legacy_binary(tmp_path):
    env, fake_bin = _base_env(tmp_path)
    _archive_downloads(tmp_path, env, fake_bin)
    target = Path(env['MDX_INSTALL_DIR']) / 'mdx'
    target.parent.mkdir()
    _write_executable(target, 'echo old-version\n')
    result = _run_install_sh(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert target.is_symlink()
    assert (target.resolve().parent / '_internal' / 'version').is_file()
    assert subprocess.check_output([str(target)], text=True).strip() == '2.1.1'
    previous = target.resolve()
    result = _run_install_sh(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert previous.is_file(), 'Keep old runtime available for running processes'
    assert subprocess.check_output([str(target)], text=True).strip() == '2.1.1'


@pytest.mark.parametrize('failure', ['checksum', 'executable', 'archive'])
def test_install_sh_preserves_existing_install_on_bad_bundle(tmp_path, failure):
    env, fake_bin = _base_env(tmp_path)
    _archive_downloads(tmp_path, env, fake_bin, broken=failure == 'executable')
    if failure == 'checksum':
        env['FAKE_ARCHIVE_HASH'] = '0' * 64
    elif failure == 'archive':
        archive = Path(env['FAKE_ARCHIVE'])
        archive.write_bytes(b'not a tar file')
        env['FAKE_ARCHIVE_HASH'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    target = Path(env['MDX_INSTALL_DIR']) / 'mdx'
    target.parent.mkdir()
    _write_executable(target, 'echo old-version\n')
    result = _run_install_sh(env)
    assert result.returncode != 0
    assert subprocess.check_output([str(target)], text=True).strip() == 'old-version'


@pytest.mark.skipif(not os.environ.get('MDX_TEST_BUNDLE_ARCHIVE'), reason='Release bundle not provided')
def test_install_sh_real_release_bundle(tmp_path):
    """Run the real release bundle through install, replacement and relocation."""
    env, fake_bin = _base_env(tmp_path)
    _archive_downloads(tmp_path, env, fake_bin)
    real_archive = Path(os.environ['MDX_TEST_BUNDLE_ARCHIVE'])
    shutil.copyfile(real_archive, env['FAKE_ARCHIVE'])
    env['FAKE_ARCHIVE_HASH'] = hashlib.sha256(real_archive.read_bytes()).hexdigest()
    for _ in range(2):
        result = _run_install_sh(env)
        assert result.returncode == 0, result.stdout + result.stderr
        target = Path(env['MDX_INSTALL_DIR']) / 'mdx'
        from mdx_cli import __version__
        assert subprocess.check_output([str(target), '--version'], text=True).strip() == __version__
        subprocess.run([str(target), '--help'], check=True, capture_output=True)
