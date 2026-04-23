import json
from unittest.mock import patch, call

from typer.testing import CliRunner

from mdx_cli.commands.vm import app
from mdx_cli.models.vm import VM

runner = CliRunner()


def _make_vm(name="test-vm", uuid="00000000-0000-0000-0000-000000000001", status="PowerON"):
    return VM(
        uuid=uuid,
        name=name,
        status=status,
        service_level="スポット仮想マシン",
    )


def test_vm_list_json():
    with patch("mdx_cli.commands.vm.list_vms", return_value=[_make_vm()]):
        with patch("mdx_cli.commands.vm.get_client"):
            result = runner.invoke(app, ["list", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1


def test_vm_show_json():
    vm = _make_vm()
    with patch("mdx_cli.commands.vm.get_vm", return_value=vm):
        with patch("mdx_cli.commands.vm.get_client"):
            result = runner.invoke(app, ["show", vm.uuid, "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["name"] == "test-vm"


def test_vm_stop_by_uuid():
    """UUID指定で1台停止"""
    vm = _make_vm()
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=[vm]):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}]) as mock_action:
            with patch("mdx_cli.commands.vm.get_client"):
                result = runner.invoke(app, ["stop", vm.uuid])
                assert result.exit_code == 0
                mock_action.assert_called_once()


def test_vm_stop_by_pattern():
    """パターン指定で複数台停止"""
    vms = [_make_vm("crawler-a-0", "uuid-1"), _make_vm("crawler-a-1", "uuid-2")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}, {}]) as mock_action:
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.questionary") as mock_q:
                    mock_q.confirm.return_value.unsafe_ask.return_value = True
                    result = runner.invoke(app, ["stop", "crawler-*", "-p", "proj-1"])
                    assert result.exit_code == 0
                    mock_action.assert_called_once()


def test_vm_start_pattern():
    """パターン指定で複数台起動"""
    vms = [_make_vm("web-0", "uuid-3"), _make_vm("web-1", "uuid-4")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}, {}]) as mock_action:
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.questionary") as mock_q:
                    mock_q.confirm.return_value.unsafe_ask.return_value = True
                    result = runner.invoke(app, ["start", "web-*", "-p", "proj-1"])
                    assert result.exit_code == 0
                    mock_action.assert_called_once()


def test_vm_destroy_single():
    """UUID指定で1台削除（停止済み）"""
    vm = _make_vm(status="PowerOFF")
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=[vm]):
        with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{"task_id": "task-1"}]):
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.questionary") as mock_q:
                    mock_q.confirm.return_value.unsafe_ask.return_value = True
                    result = runner.invoke(app, ["destroy", vm.uuid, "--no-wait"])
                    assert result.exit_code == 0


# --- トークン事前リフレッシュ ---


def test_refresh_token_proactive_saves_new_token():
    """リフレッシュ成功時は新トークンを保存する。"""
    import httpx
    import respx

    from mdx_cli.commands.vm import _refresh_token_proactive
    from mdx_cli.credentials.store import CredentialStore

    mock_store = patch("mdx_cli.commands.vm.CredentialStore").start()
    instance = mock_store.return_value
    instance.load_token.return_value = "old-token"

    with respx.mock(base_url="https://oprpl.mdx.jp") as router:
        router.post("/api/refresh/").mock(
            return_value=httpx.Response(200, json={"token": "new-token"})
        )
        _refresh_token_proactive()
        instance.save_token.assert_called_once_with("new-token")

    patch.stopall()


def test_refresh_token_proactive_no_token_does_nothing():
    """トークン未保存なら何もしない。"""
    from mdx_cli.commands.vm import _refresh_token_proactive

    with patch("mdx_cli.commands.vm.CredentialStore") as mock_store:
        instance = mock_store.return_value
        instance.load_token.return_value = None
        _refresh_token_proactive()
        instance.save_token.assert_not_called()


def test_refresh_token_proactive_failure_does_not_raise():
    """リフレッシュ失敗時も例外を投げず既存トークンを保持する。"""
    import httpx
    import respx

    from mdx_cli.commands.vm import _refresh_token_proactive

    with patch("mdx_cli.commands.vm.CredentialStore") as mock_store:
        instance = mock_store.return_value
        instance.load_token.return_value = "old-token"

        with respx.mock(base_url="https://oprpl.mdx.jp") as router:
            router.post("/api/refresh/").mock(
                return_value=httpx.Response(400, json={"detail": "expired"})
            )
            _refresh_token_proactive()
            instance.save_token.assert_not_called()


def test_parallel_vm_action_refreshes_token_before_bulk():
    """バルク操作の前に事前リフレッシュが呼ばれる。"""
    vm = _make_vm()
    with patch("mdx_cli.commands.vm._refresh_token_proactive") as mock_refresh:
        with patch("mdx_cli.commands.vm.parallel_post", return_value=[{}]):
            with patch("mdx_cli.commands.vm._get_token_and_base", return_value=("tok", "https://oprpl.mdx.jp")):
                from mdx_cli.commands.vm import _parallel_vm_action
                _parallel_vm_action([vm], lambda v: f"/api/vm/{v.uuid}/stop/", "停止中")
                mock_refresh.assert_called_once()


def test_parallel_vm_action_refreshes_once_for_small_batch():
    """30台以下のバルク操作はリフレッシュ1回だけ。"""
    vms = [_make_vm(f"vm-{i}", f"uuid-{i}") for i in range(30)]
    with patch("mdx_cli.commands.vm._refresh_token_proactive") as mock_refresh:
        with patch("mdx_cli.commands.vm.parallel_post", return_value=[{}] * 30):
            with patch("mdx_cli.commands.vm._get_token_and_base", return_value=("tok", "https://oprpl.mdx.jp")):
                from mdx_cli.commands.vm import _parallel_vm_action
                _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/stop/", "停止中")
                assert mock_refresh.call_count == 1


def test_parallel_vm_action_refreshes_per_chunk_for_large_batch():
    """31台以上のバルク操作は30台ごとにリフレッシュ。"""
    vms = [_make_vm(f"vm-{i}", f"uuid-{i}") for i in range(75)]

    with patch("mdx_cli.commands.vm._refresh_token_proactive") as mock_refresh:
        with patch("mdx_cli.commands.vm.parallel_post") as mock_post:
            mock_post.side_effect = [
                [{}] * 30,
                [{}] * 30,
                [{}] * 15,
            ]
            with patch("mdx_cli.commands.vm._get_token_and_base", return_value=("tok", "https://oprpl.mdx.jp")):
                from mdx_cli.commands.vm import _parallel_vm_action
                results = _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/stop/", "停止中")
                # 75 / 30 = 3 チャンク（30, 30, 15）→ refresh 3回
                assert mock_refresh.call_count == 3
                assert mock_post.call_count == 3
                assert len(results) == 75


# --- deploy コマンド ---

from pathlib import Path

from mdx_cli.models.template import Template
from mdx_cli.models.network import Segment
from mdx_cli.models.vm import VMDeployResponse


def _make_template():
    return Template(
        uuid="tmpl-1",
        name="Ubuntu 22.04",
        template_name="ubuntu-2204",
        os_type="Linux",
        os_name="Ubuntu",
        os_version="22.04",
        login_username="mdxuser",
        lower_limit_disk=40,
    )


def _make_segment():
    return Segment(uuid="seg-1", name="default-segment")


def test_vm_deploy_single_digit_range_aggregates_to_one_request(tmp_path):
    """{0-9} は [0-9] として1リクエストに集約され、10 task_id を全て収集する。"""
    key_file = tmp_path / "id.pub"
    key_file.write_text("ssh-rsa AAAA...")

    deploy_resp = VMDeployResponse(
        task_id=[f"task-{i}" for i in range(10)]
    )
    captured_requests: list = []

    def mock_deploy(client, req):
        captured_requests.append(req)
        return deploy_resp

    with patch("mdx_cli.commands.vm.list_templates", return_value=[_make_template()]):
        with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
            with patch("mdx_cli.commands.vm.deploy_vm", side_effect=mock_deploy) as mock_d:
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                        result = runner.invoke(app, [
                            "deploy",
                            "-t", "Ubuntu",
                            "-n", "test-{0-9}",
                            "--pack-type", "cpu",
                            "--pack-num", "4",
                            "--disk", "40",
                            "--service-level", "spot",
                            "-k", str(key_file),
                            "-y",
                            "--no-wait",
                        ])
                        assert result.exit_code == 0, result.output
                        assert mock_d.call_count == 1
                        assert captured_requests[0].vm_name == "test-[0-9]"


def test_vm_deploy_alpha_with_digit_aggregates_to_three_requests(tmp_path):
    """{a-c}-{0-9} は3リクエストに集約され、各々10 task_id で合計30台。"""
    key_file = tmp_path / "id.pub"
    key_file.write_text("ssh-rsa AAAA...")

    captured_requests: list = []

    def mock_deploy(client, req):
        captured_requests.append(req)
        return VMDeployResponse(task_id=[f"task-{req.vm_name}-{i}" for i in range(10)])

    with patch("mdx_cli.commands.vm.list_templates", return_value=[_make_template()]):
        with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
            with patch("mdx_cli.commands.vm.deploy_vm", side_effect=mock_deploy) as mock_d:
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                        result = runner.invoke(app, [
                            "deploy",
                            "-t", "Ubuntu",
                            "-n", "worker-{a-c}-{0-9}",
                            "--pack-type", "cpu",
                            "--pack-num", "4",
                            "--disk", "40",
                            "--service-level", "spot",
                            "-k", str(key_file),
                            "-y",
                            "--no-wait",
                        ])
                        assert result.exit_code == 0, result.output
                        assert mock_d.call_count == 3
                        vm_names = [r.vm_name for r in captured_requests]
                        assert vm_names == [
                            "worker-a-[0-9]",
                            "worker-b-[0-9]",
                            "worker-c-[0-9]",
                        ]


def test_vm_deploy_zero_padded_does_not_aggregate(tmp_path):
    """{00-09} は API非対応のためクライアント側で展開（10リクエスト）。"""
    key_file = tmp_path / "id.pub"
    key_file.write_text("ssh-rsa AAAA...")

    captured_requests: list = []

    def mock_deploy(client, req):
        captured_requests.append(req)
        return VMDeployResponse(task_id=[f"task-{req.vm_name}"])

    with patch("mdx_cli.commands.vm.list_templates", return_value=[_make_template()]):
        with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
            with patch("mdx_cli.commands.vm.deploy_vm", side_effect=mock_deploy) as mock_d:
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                        result = runner.invoke(app, [
                            "deploy",
                            "-t", "Ubuntu",
                            "-n", "node-{00-09}",
                            "--pack-type", "cpu",
                            "--pack-num", "4",
                            "--disk", "40",
                            "--service-level", "spot",
                            "-k", str(key_file),
                            "-y",
                            "--no-wait",
                        ])
                        assert result.exit_code == 0, result.output
                        assert mock_d.call_count == 10
                        vm_names = [r.vm_name for r in captured_requests]
                        assert vm_names[0] == "node-00"
                        assert vm_names[-1] == "node-09"
