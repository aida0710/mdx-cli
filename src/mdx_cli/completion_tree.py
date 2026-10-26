"""タブ補完用に、コマンド構造を保存・復元する。

補完の要求は Tab のたびに mdx を起動する。本体を読み込むと httpx・questionary などで
0.5 秒ほどかかるため、コマンド・オプションの構造だけを completion_tree_data.py に保存しておき、
補完のときはそこから処理を持たないコマンドを組み立てて typer の補完に答えさせる。
候補の出し方・シェルごとの出力形式は typer のものをそのまま使う。

保存し直すとき: uv run python -m mdx_cli.completion_tree
"""

import pprint
from pathlib import Path

# click を直接使わない。typer 0.26 以降は click を内部（typer._click）に持ち、click が入っていないことがある。
# TyperChoice は非公開のモジュールにあるが、0.24・0.27 とも同じ引数で作れる（本体との一致はテストで確かめる）
from typer._types import TyperChoice
from typer.core import TyperArgument, TyperCommand, TyperGroup, TyperOption

DATA_PATH = Path(__file__).with_name("completion_tree_data.py")


def _dump_param_type(param_type) -> dict:
    if getattr(param_type, "choices", None) is not None:
        return {
            "kind": "choice",
            "choices": list(param_type.choices),
            "case_sensitive": param_type.case_sensitive,
        }
    # 文字列・数値は候補を出さず、typer のパスはファイル名の補完をシェルに任せるので区別しない
    return {"kind": "text"}


def _dump_param(param) -> dict:
    if isinstance(param, TyperOption):
        if param.secondary_opts:
            raise ValueError(f"--x/--no-x 形式のオプションは保存できません: {param.opts}")
        return {
            "kind": "option",
            "name": param.name,
            "opts": list(param.opts),
            "help": param.help,
            "is_flag": param.is_flag,
            "multiple": param.multiple,
            "count": param.count,
            "nargs": param.nargs,
            "hidden": param.hidden,
            "type": _dump_param_type(param.type),
        }
    return {
        "kind": "argument",
        "name": param.name,
        "nargs": param.nargs,
        "type": _dump_param_type(param.type),
    }


def dump_command_tree(command) -> dict:
    """typer のコマンドから、補完に要る情報だけを辞書にする。"""
    tree = {
        "name": command.name,
        "help": command.help,
        "short_help": command.short_help,
        "hidden": command.hidden,
        "no_args_is_help": command.no_args_is_help,
        "params": [_dump_param(param) for param in command.params],
    }
    if isinstance(command, TyperGroup):
        tree["invoke_without_command"] = command.invoke_without_command
        tree["commands"] = [dump_command_tree(child) for child in command.commands.values()]
    return tree


def _build_param_type(saved: dict):
    if saved["kind"] == "choice":
        return TyperChoice(saved["choices"], case_sensitive=saved["case_sensitive"])
    return None  # 既定の文字列型


def _build_param(saved: dict):
    param_type = _build_param_type(saved["type"])
    if saved["kind"] == "argument":
        return TyperArgument(
            param_decls=[saved["name"]], type=param_type, nargs=saved["nargs"], required=False
        )
    return TyperOption(
        param_decls=[saved["name"], *saved["opts"]],
        type=None if saved["is_flag"] else param_type,
        help=saved["help"],
        is_flag=saved["is_flag"] or None,
        multiple=saved["multiple"],
        count=saved["count"],
        nargs=saved["nargs"],
        hidden=saved["hidden"],
    )


def build_command(tree: dict):
    """保存した辞書から、処理を持たない（補完にだけ使う）コマンドを組み立てる。"""
    shared = {
        "name": tree["name"],
        "help": tree["help"],
        "short_help": tree["short_help"],
        "hidden": tree["hidden"],
        "no_args_is_help": tree["no_args_is_help"],
        "params": [_build_param(param) for param in tree["params"]],
    }
    if "commands" not in tree:
        return TyperCommand(**shared)
    return TyperGroup(
        **shared,
        invoke_without_command=tree["invoke_without_command"],
        commands=[build_command(child) for child in tree["commands"]],
    )


def complete_from_saved_tree(complete_var: str) -> None:
    """保存した構造で補完の要求に答える。typer が候補を出力して終了する。"""
    from typer.completion import completion_init

    from mdx_cli.completion_tree_data import COMMAND_TREE

    completion_init()
    build_command(COMMAND_TREE).main(complete_var=complete_var)


def save_command_tree() -> None:
    import typer.main

    from mdx_cli.main import app

    tree = dump_command_tree(typer.main.get_command(app))
    DATA_PATH.write_text(
        '"""タブ補完用のコマンド構造。uv run python -m mdx_cli.completion_tree で作り直す（手で直さない）。"""\n\n'
        f"COMMAND_TREE = {pprint.pformat(tree, width=110, sort_dicts=False)}\n"
    )


if __name__ == "__main__":
    save_command_tree()
