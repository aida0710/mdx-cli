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


def test_install_script_usage_matches_own_filename():
    """インストールスクリプトの usage が自分自身のファイル名を案内している。"""
    script = ROOT / "agent-skill-install.sh"
    assert _referenced_scripts(script.read_text()) == {script.name}
