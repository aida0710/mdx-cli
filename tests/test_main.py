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
