import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def _release_repo(tmp_path: Path, version: str = "2.1.0") -> Path:
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    (repo / "src/mdx_cli").mkdir(parents=True)
    (repo / "release.sh").write_bytes((ROOT / "release.sh").read_bytes())
    (repo / "release.sh").chmod(0o755)
    (repo / "pyproject.toml").write_text(f'[project]\nname = "mdx-cli"\nversion = "{version}"\n')
    (repo / "src/mdx_cli/__init__.py").write_text(f'__version__ = "{version}"\n')
    (repo / "uv.lock").write_text(f'[[package]]\nname = "mdx-cli"\nversion = "{version}"\n')

    _run("git", "init", "-b", "main", cwd=repo)
    _run("git", "config", "user.name", "Release Test", cwd=repo)
    _run("git", "config", "user.email", "release-test@example.invalid", cwd=repo)
    _run("git", "add", ".", cwd=repo)
    _run("git", "commit", "-m", "初期状態", cwd=repo)
    _run("git", "tag", "-a", f"v{version}", "-m", f"v{version}", cwd=repo)
    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _run("git", "remote", "add", "origin", str(remote), cwd=repo)
    _run("git", "push", "-u", "origin", "main", "--tags", cwd=repo)
    return repo


def _release(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C.UTF-8"
    return subprocess.run(
        ["sh", "release.sh", *args],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_dry_run_accepts_only_newer_version_without_changes(tmp_path):
    repo = _release_repo(tmp_path)
    before = _run("git", "rev-parse", "HEAD", cwd=repo).stdout

    result = _release(repo, "--dry-run", "2.2.0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "v2.1.0 → v2.2.0" in result.stdout
    assert "変更せず終了" in result.stdout
    assert _run("git", "rev-parse", "HEAD", cwd=repo).stdout == before
    assert _run("git", "status", "--porcelain", cwd=repo).stdout == ""


def test_release_rejects_same_or_older_version(tmp_path):
    repo = _release_repo(tmp_path)

    for version in ("2.1.0", "2.0.9"):
        result = _release(repo, "--dry-run", version)
        assert result.returncode != 0
        assert "より大きく" in result.stderr


def test_release_compares_semver_components_numerically(tmp_path):
    repo = _release_repo(tmp_path, version="2.9.9")

    result = _release(repo, "--dry-run", "2.10.0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "v2.9.9 → v2.10.0" in result.stdout


def test_release_rejects_invalid_semver_and_dirty_worktree(tmp_path):
    repo = _release_repo(tmp_path)

    invalid = _release(repo, "--dry-run", "v2.2")
    assert invalid.returncode != 0
    assert "SemVer" in invalid.stderr

    (repo / "untracked.txt").write_text("dirty")
    dirty = _release(repo, "--dry-run", "2.2.0")
    assert dirty.returncode != 0
    assert "clean" in dirty.stderr


def test_release_script_preserves_publish_order_and_is_documented():
    script = (ROOT / "release.sh").read_text()
    assert os.access(ROOT / "release.sh", os.X_OK)
    assert script.index("git push origin main") < script.index('wait_for_run test.yml "$release_commit"')
    assert script.index('wait_for_run test.yml "$release_commit"') < script.index('git tag -a "$tag"')
    assert script.index('git push origin "$tag"') < script.index('wait_for_run release.yml "$release_commit"')
    assert "uv run --no-sync pytest -q" in script
    assert "uv run --no-sync ruff check ." in script
    assert "./release.sh --dry-run" in (ROOT / "README.md").read_text()
