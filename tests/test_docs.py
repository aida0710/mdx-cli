"""ドキュメントとリポジトリ実体の整合性テスト"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT_RE = re.compile(r"[\w.-]*install\.sh")


def _referenced_scripts(text: str) -> set[str]:
    return set(_SCRIPT_RE.findall(text))


def test_readme_install_script_references_exist():
    """README が案内するインストールスクリプト名が実在する。

    リネーム時に README を直し忘れると
    `curl -fsSL .../xxx-install.sh | sh` が 404 を引く。curl はエラーを
    出すがパイプ先の sh は空入力を正常終了するため、終了ステータスは 0 に
    なりインストールされていないのに成功したように見える。
    """
    referenced = _referenced_scripts((ROOT / "README.md").read_text())
    assert referenced, "README にインストールスクリプトの案内がありません"
    for name in referenced:
        assert (ROOT / name).exists(), f"README が参照する {name} が存在しません"


def test_readme_downloads_installers_from_same_release_channel_as_binaries():
    """mainだけが先行してlatestバイナリと不整合になる公開窓を作らない。"""
    readme = (ROOT / "README.md").read_text()
    assert "releases/latest/download/install.sh" in readme
    assert "releases/latest/download/install.ps1" in readme
    assert "raw.githubusercontent.com/aida0710/mdx-cli/main/install" not in readme


def test_install_script_usage_matches_own_filename():
    """インストールスクリプトの usage が自分自身のファイル名を案内している。"""
    script = ROOT / "agent-skill-install.sh"
    assert _referenced_scripts(script.read_text()) == {script.name}


def test_version_matches_pyproject():
    """mdx_cli.__version__ と pyproject.toml の version が一致する。

    リリースタグはこの値を基準に打つため、ズレるとバイナリと Release の
    バージョン表示が食い違う。
    """
    import tomllib

    from mdx_cli import __version__

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert __version__ == pyproject["project"]["version"]


def test_release_version_is_2_0_0():
    import tomllib

    from mdx_cli import __version__

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert __version__ == "2.0.0"
    assert pyproject["project"]["version"] == "2.0.0"
    assert not any(dependency.startswith("typer[all]") for dependency in pyproject["project"]["dependencies"])

    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    root_package = next(package for package in lock["package"] if package["name"] == "mdx-cli")
    assert root_package["version"] == "2.0.0"


def test_install_script_assets_match_release_workflow():
    """install.sh / install.ps1 が取得する成果物名が Release ワークフローの生成物と一致する。

    名前がズレるとインストーラがリリース資産を 404 で引き、
    ユーザー側には「ダウンロード失敗」としか見えない。
    """
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    built = set(re.findall(r"artifact: (mdx-[\w-]+)", workflow))
    assert built, "release.yml にビルド成果物名が見つかりません"

    for script in ("install.sh", "install.ps1"):
        used = set(re.findall(r"mdx-(?:darwin|linux|windows)-\w+", (ROOT / script).read_text()))
        assert used, f"{script} が成果物名を参照していません"
        assert used <= built, f"{script} が Release にない成果物を参照しています: {sorted(used - built)}"


def test_release_workflow_runs_tests_and_lint_before_building():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    verify_job = workflow[workflow.index("  verify:"):workflow.index("  build:")]
    assert "uv run --no-sync pytest" in verify_job
    assert "uv run --no-sync ruff check ." in verify_job
