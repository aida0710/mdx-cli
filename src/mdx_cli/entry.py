"""mdx コマンドの入口。タブ補完の要求だけは、本体を読み込まずに保存したコマンド構造で答える。"""

import os

# typer がプログラム名 mdx から決める補完用の環境変数。値は complete_bash・source_bash など
_COMPLETE_VAR = "_MDX_COMPLETE"


def cli() -> None:
    # source_*（補完スクリプトの出力）は本体で処理する。毎回の Tab で呼ばれるのは complete_* だけ
    if os.environ.get(_COMPLETE_VAR, "").startswith("complete_"):
        from mdx_cli.completion_tree import complete_from_saved_tree

        complete_from_saved_tree(complete_var=_COMPLETE_VAR)
        return

    from mdx_cli.main import cli as run_main

    run_main()


if __name__ == "__main__":
    cli()
