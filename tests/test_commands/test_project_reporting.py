"""CLIからHTTP境界まで、合成レスポンスで取得・表示の契約を検証する。"""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from mdx_cli.commands.project import app

runner = CliRunner()

# rowspan/colspan・単位・小数桁は合成データ。実レポートの形式を断定しない。
REPORT_HTML = """<html><head><style>hidden style</style></head><body>
<table><caption>資源利用状況</caption><thead><tr>
<th>資源種別</th><th>利用資源</th><th>単価</th><th>のべ使用量</th><th>消費ポイント</th>
</tr></thead><tbody>
<tr><td rowspan="2">CPU &amp; GPU</td><td>cpu</td><td>0.01</td><td>10 pack h</td><td>0.10</td></tr>
<tr><td>gpu</td><td>1.00</td><td>1,234.50</td><td>1,234.50</td></tr>
<tr><td colspan="4">合計</td><td>1,234.60</td></tr>
</tbody></table><script>secret_script()</script></body></html>"""


@pytest.fixture(autouse=True)
def mock_client(mocker):
    clients = []

    def create(**kwargs):
        client = httpx.Client(base_url="https://oprpl.mdx.jp")
        clients.append(client)
        return client

    mocked = mocker.patch("mdx_cli.commands.project.get_client", side_effect=create)
    mocker.patch("mdx_cli.commands._common.get_store").return_value.load_project_id.return_value = "saved"
    yield mocked
    for client in clients:
        client.close()


@respx.mock
def test_tenants_list_and_select(mocker):
    respx.get("/api/project/assigned/").respond(200, json=[
        {"name": "Empty", "projects": []},
        {"name": "Tenant", "projects": [{"uuid": "p1", "name": "Project", "type": 0}]},
    ])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "p1" in result.output and "Tenant" in result.output
    result = runner.invoke(app, ["list", "--json"])
    assert json.loads(result.stdout)[1]["projects"][0]["uuid"] == "p1"
    mocker.patch("mdx_cli.commands._common.questionary.text").return_value.unsafe_ask.return_value = "1"
    store = mocker.patch("mdx_cli.commands.project.get_store").return_value
    result = runner.invoke(app, ["select"])
    assert result.exit_code == 0, result.output
    store.save_project_id.assert_called_once_with("p1")


@respx.mock
def test_show_all_project_information():
    respx.get("/api/project/p1/summary/").respond(200, json={
        "uuid": "p1", "name": "Project", "type": "normal", "applicant": "Applicant",
        "begin": "2026-04-01", "limit": "2027-03-31",
    })
    result = runner.invoke(app, ["show", "p1"])
    assert result.exit_code == 0, result.output
    for value in ["p1", "normal", "Applicant", "2026-04-01", "2027-03-31"]:
        assert value in result.output


@respx.mock
def test_resources_differentiates_requested_used_allocated():
    respx.get("/api/project/saved/resources/").respond(200, json={
        "cpu_pack_max": 100, "cpu_pack": 12, "cpu_pack_max_current": 40,
        "cpu_pack_future": 30, "cpu_pack_rmin": 5, "gpu_pack": 0, "global_ip": 3,
    })
    result = runner.invoke(app, ["resources"])
    assert result.exit_code == 0, result.output
    for value in ["要求量", "使用量", "割当量", "翌月割当量", "Rmin", "100", "12", "40", "30"]:
        assert value in result.output


@respx.mock
def test_users_json_metadata_and_env_project(monkeypatch, mock_client):
    monkeypatch.setenv("MDX_PROJECT_ID", "env-project")
    route = respx.get("/api/user/project/env-project/").respond(200, json={"count": 0, "results": []})
    result = runner.invoke(app, ["users", "--page", "3", "--page-size", "20", "--ordering=-username",
                                 "--username", "A&B", "--email", "a+b@example.test", "--auth", "0", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"count": 0, "results": []}
    assert dict(route.calls[0].request.url.params) == {
        "page": "3", "page_size": "20", "ordering": "-username", "username": "A&B",
        "email": "a+b@example.test", "auth": "0",
    }
    mock_client.assert_called_once_with(silent=True)


@respx.mock
def test_points_show_last_consumed_and_empty_results():
    respx.get("/api/project/p1/point/").respond(200, json={"lastConsumed": "2026-09-12 00:00:00", "results": []})
    result = runner.invoke(app, ["points", "-p", "p1"])
    assert result.exit_code == 0, result.output
    assert "2026-09-12 00:00:00" in result.output


@respx.mock
def test_usage_default_and_structured_json(mock_client):
    route = respx.post("/api/project/saved/resource_usage/").respond(200, json={"html": REPORT_HTML, "err_msg": ""})
    result = runner.invoke(app, ["usage", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["html"] == REPORT_HTML
    table = data["tables"][0]
    assert table["caption"] == "資源利用状況"
    assert table["headers"][0] == "資源種別"
    assert table["rows"][1] == ["CPU & GPU", "gpu", "1.00", "1,234.50", "1,234.50"]
    assert table["rows"][2] == ["合計", "合計", "合計", "合計", "1,234.60"]
    assert json.loads(route.calls[0].request.content) == {"input_type": 1, "start": "", "end": "", "lang": "jp"}
    mock_client.assert_called_once_with(silent=True)


@respx.mock
@pytest.mark.parametrize("days,input_type", [(7, 1), (30, 2), (90, 3), (365, 4)])
def test_usage_preset(days, input_type):
    route = respx.post("/api/project/p1/resource_usage/").respond(200, json={"html": REPORT_HTML})
    result = runner.invoke(app, ["usage", "-p", "p1", "--days", str(days)])
    assert result.exit_code == 0, result.output
    assert "1,234.60" in result.output
    assert "<table>" not in result.output and "secret_script" not in result.output
    assert json.loads(route.calls[0].request.content)["input_type"] == input_type


@respx.mock
def test_usage_custom_period_html_and_file(tmp_path):
    route = respx.post("/api/project/saved/resource_usage/").respond(200, json={"html": REPORT_HTML})
    args = ["usage", "--start", "2026-09-05 00", "--end", "2026-09-12 23", "--lang", "en"]
    result = runner.invoke(app, [*args, "--html"])
    assert result.exit_code == 0, result.output
    assert result.stdout.rstrip("\n") == REPORT_HTML
    assert json.loads(route.calls[0].request.content) == {
        "input_type": 0, "start": "2026-09-05 00", "end": "2026-09-12 23", "lang": "en",
    }
    path = tmp_path / "report.html"
    result = runner.invoke(app, [*args, "-o", str(path)])
    assert result.exit_code == 0, result.output
    assert path.read_text() == REPORT_HTML


@pytest.mark.parametrize("args", [
    ["usage", "--days", "8"], ["usage", "--start", "2026-09-05 00"],
    ["usage", "--end", "2026-09-12 00"],
    ["usage", "--start", "2026-02-30 00", "--end", "2026-09-12 00"],
    ["usage", "--start", "2026-9-05 00", "--end", "2026-09-12 00"],
    ["usage", "--start", "2026-09-05 24", "--end", "2026-09-12 00"],
    ["usage", "--start", "2026-09-12 00", "--end", "2026-09-05 00"],
    ["usage", "--days", "7", "--start", "2026-09-05 00", "--end", "2026-09-12 00"],
    ["usage", "--lang", "ja"], ["usage", "--json", "--html"],
    ["usage", "--json", "-o", "report.html"],
    ["users", "--page", "0"], ["users", "--page-size", "0"], ["users", "--page-size", "101"],
])
def test_invalid_options_do_not_contact_api(args, mock_client):
    result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    mock_client.assert_not_called()


@respx.mock
@pytest.mark.parametrize("json_mode", [False, True])
def test_usage_application_error_is_failure(json_mode, tmp_path):
    respx.post("/api/project/saved/resource_usage/").respond(200, json={"html": None, "err_msg": "期間が不正です"})
    result = runner.invoke(app, ["usage", *( ["--json"] if json_mode else [])])
    assert result.exit_code == 1, result.output
    assert "期間が不正です" in result.stderr
    assert result.stdout == ""


@respx.mock
def test_usage_error_does_not_overwrite_output(tmp_path):
    path = tmp_path / "report.html"
    path.write_text("previous report")
    respx.post("/api/project/saved/resource_usage/").respond(200, json={"html": REPORT_HTML, "err_msg": "失敗"})
    result = runner.invoke(app, ["usage", "-o", str(path)])
    assert result.exit_code == 1
    assert path.read_text() == "previous report"


@respx.mock
@pytest.mark.parametrize("payload", [{}, {"html": ""}, {"html": None}, {"html": "  "}])
def test_usage_missing_html_is_failure(payload):
    respx.post("/api/project/saved/resource_usage/").respond(200, json=payload)
    result = runner.invoke(app, ["usage", "--json"])
    assert result.exit_code == 1
    assert "HTML" in result.stderr
    assert result.stdout == ""


@respx.mock
def test_usage_without_tables_can_be_recovered_as_html_or_json():
    respx.post("/api/project/saved/resource_usage/").respond(200, json={"html": "<p>No usage</p>"})
    result = runner.invoke(app, ["usage"])
    assert result.exit_code == 1
    assert "表が見つかりません" in result.stderr
    result = runner.invoke(app, ["usage", "--json"])
    assert json.loads(result.stdout)["tables"] == []
    result = runner.invoke(app, ["usage", "--html"])
    assert result.stdout == "<p>No usage</p>"


@respx.mock
def test_show_explicit_id_overrides_env(monkeypatch):
    monkeypatch.setenv("MDX_PROJECT_ID", "env-project")
    respx.get("/api/project/p1/summary/").respond(200, json={"uuid": "p1", "name": "P1"})
    result = runner.invoke(app, ["show", "p1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["uuid"] == "p1"


@respx.mock
def test_show_saved_project():
    respx.get("/api/project/saved/summary/").respond(200, json={"uuid": "saved", "name": "Saved"})
    result = runner.invoke(app, ["show", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["uuid"] == "saved"


@respx.mock
def test_overview_all():
    sections = ["resource", "resource_list", "vm", "spot_vm", "guarantee_vm"]
    for section in sections:
        respx.get(f"/api/project/saved/overview/{section}/").respond(200, json={"section": section})
    result = runner.invoke(app, ["overview", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {section: {"section": section} for section in sections}


@respx.mock
def test_overview_resource_list():
    respx.get("/api/project/saved/overview/resource_list/").respond(200, json=[{"name": "cpu", "value": 3}])
    result = runner.invoke(app, ["overview", "--kind", "resource_list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [{"name": "cpu", "value": 3}]
