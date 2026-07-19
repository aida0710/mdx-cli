import logging

import httpx
import typer

from mdx_cli.api.spinner import stop_active_spinner
from mdx_cli.commands.auth import app as auth_app
from mdx_cli.commands.network import app as network_app
from mdx_cli.commands.project import app as project_app
from mdx_cli.commands.task import app as task_app
from mdx_cli.commands.template import app as template_app
from mdx_cli.commands.vm import app as vm_app

app = typer.Typer(help="MDX 1 CLI ツール")

app.add_typer(auth_app, name="auth")
app.add_typer(project_app, name="project")
app.add_typer(vm_app, name="vm")
app.add_typer(network_app, name="network")
app.add_typer(template_app, name="template")
app.add_typer(task_app, name="task")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="詳細ログ出力"),
) -> None:
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s %(name)s: %(message)s",
        )


def cli() -> None:
    """エントリポイント。httpxのエラーをトレースバックではなく短い表示にする。

    詳細を調べたいときは --verbose でDEBUGログを有効にして再実行する。
    """
    from mdx_cli.console import err_console

    try:
        app()
    except httpx.HTTPStatusError as e:
        stop_active_spinner()
        resp = e.response
        req = e.request
        err_console.print(
            f"[red]APIエラー: {resp.status_code} {resp.reason_phrase} ({req.method} {req.url})[/red]"
        )
        raise SystemExit(1)
    except httpx.ConnectError as e:
        stop_active_spinner()
        err_console.print(f"[red]接続できません: {e}（VPN接続を確認してください）[/red]")
        raise SystemExit(1)
    except httpx.TimeoutException as e:
        stop_active_spinner()
        err_console.print(f"[red]リクエストがタイムアウトしました: {e}[/red]")
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
