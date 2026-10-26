import os
import subprocess
import sys

import pytest
import typer.main

from mdx_cli.completion_tree import build_command, dump_command_tree
from mdx_cli.completion_tree_data import COMMAND_TREE
from mdx_cli.main import app

COMPLETE_VAR = "_MDX_COMPLETE"


def _command_paths(tree: dict, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], dict]]:
    paths = [(path, tree)]
    for child in tree.get("commands", []):
        paths.extend(_command_paths(child, (*path, child["name"])))
    return paths


def _completion_cases() -> list[tuple[str, ...]]:
    """全コマンドについて、サブコマンド名・オプション名・オプションの値を補完する位置を作る。"""
    cases = []
    for path, node in _command_paths(COMMAND_TREE):
        incompletes = {"", "-", "--"} | {child["name"][0] for child in node.get("commands", [])}
        cases.extend((*path, incomplete) for incomplete in sorted(incompletes))
        for param in node["params"]:
            if param["kind"] == "option" and not param["is_flag"]:
                cases.append((*path, param["opts"][0], ""))
    return cases


def _completion_env(shell: str, words: tuple[str, ...]) -> dict[str, str]:
    """typer の補完スクリプトがシェルごとに渡す環境変数を再現する。"""
    line = " ".join(("mdx", *words))
    if shell == "bash":
        return {COMPLETE_VAR: "complete_bash", "COMP_WORDS": line, "COMP_CWORD": str(len(words))}
    env = {COMPLETE_VAR: f"complete_{shell}", "_TYPER_COMPLETE_ARGS": line}
    if shell == "fish":
        env["_TYPER_COMPLETE_FISH_ACTION"] = "get-args"
    return env


def _run_completion(command, env: dict[str, str], monkeypatch, capsys) -> str:
    with monkeypatch.context() as patched:
        for key, value in env.items():
            patched.setenv(key, value)
        with pytest.raises(SystemExit):
            command.main(args=[], prog_name="mdx", complete_var=COMPLETE_VAR)
    return capsys.readouterr().out


def test_saved_tree_matches_current_commands():
    """保存したコマンド構造が今のコマンドと一致する（ずれたら python -m mdx_cli.completion_tree で作り直す）"""
    assert dump_command_tree(typer.main.get_command(app)) == COMMAND_TREE


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_saved_tree_completes_same_as_app(shell, monkeypatch, capsys):
    """保存した構造からの補完は、本体の補完と同じ候補を同じ形式で返す"""
    app_command = typer.main.get_command(app)
    saved_command = build_command(COMMAND_TREE)
    mismatches = []
    for words in _completion_cases():
        env = _completion_env(shell, words)
        expected = _run_completion(app_command, env, monkeypatch, capsys)
        actual = _run_completion(saved_command, env, monkeypatch, capsys)
        if actual != expected:
            mismatches.append((words, expected, actual))
    assert mismatches == []


def test_entry_answers_completion_without_loading_app():
    """入口は補完の要求に、本体と通信ライブラリを読み込まずに答える"""
    script = (
        "import atexit, sys\n"
        "atexit.register(lambda: print(sorted({'mdx_cli.main', 'httpx', 'questionary'} & set(sys.modules)),"
        " file=sys.stderr))\n"
        "sys.argv = ['mdx']\n"
        "from mdx_cli.entry import cli\n"
        "cli()\n"
    )
    env = {**os.environ, **_completion_env("bash", ("vm", "s"))}
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)

    assert result.stdout.split() == ["show", "start", "stop", "shutdown", "sync", "ssh"]
    assert result.stderr.strip() == "[]"
