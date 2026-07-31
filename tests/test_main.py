from typer.testing import CliRunner

from mdx_cli.main import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "project" in result.output
    assert "vm" in result.output
    assert "network" in result.output
    assert "template" in result.output
    assert "task" in result.output


def test_auth_help():
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "logout" in result.output
    assert "status" in result.output


def test_vm_help():
    result = runner.invoke(app, ["vm", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "deploy" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "destroy" in result.output


# --- トップレベルのAPIエラーハンドリング ---


def _http_status_error(status_code: int):
    import httpx

    req = httpx.Request("GET", "https://oprpl.mdx.jp/api/vm/x/")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError("error", request=req, response=resp)


def test_cli_formats_http_status_error(capsys):
    """APIの4xx/5xxはトレースバックではなく短いエラー表示で終了する。"""
    from unittest.mock import patch

    import pytest

    from mdx_cli.main import cli

    with patch("mdx_cli.main.app", side_effect=_http_status_error(404)):
        with pytest.raises(SystemExit) as exc_info:
            cli()
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "APIエラー: 404" in err
    assert "/api/vm/x/" in err


def test_cli_formats_connect_error(capsys):
    """接続エラーはVPN確認を促す表示で終了する。"""
    from unittest.mock import patch

    import httpx
    import pytest

    from mdx_cli.main import cli

    with patch("mdx_cli.main.app", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(SystemExit) as exc_info:
            cli()
    assert exc_info.value.code == 1
    assert "VPN" in capsys.readouterr().err


def test_cli_formats_other_httpx_errors(capsys):
    """ReadError 等の httpx エラーもトレースバックを出さずに終了する。

    ConnectError / TimeoutException / HTTPStatusError だけを捕捉していると
    ReadError・RemoteProtocolError・ProxyError が素のトレースバックになる。
    """
    from unittest.mock import patch

    import httpx
    import pytest

    from mdx_cli.main import cli

    with patch("mdx_cli.main.app", side_effect=httpx.RemoteProtocolError("broken")):
        with pytest.raises(SystemExit) as exc_info:
            cli()
    assert exc_info.value.code == 1
    assert "broken" in capsys.readouterr().err


def test_cli_passes_through_normal_exit():
    """正常終了はそのまま（--help 等）。"""
    from unittest.mock import patch

    from mdx_cli.main import cli

    with patch("mdx_cli.main.app", return_value=None):
        cli()  # 例外なく戻る
