import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.vm import _list_pubkeys, _pubkey_preview, app
from mdx_cli.models.network import Segment
from mdx_cli.models.template import Template
from mdx_cli.models.vm import VM, VMDeployResponse

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


# --- reconfigure 均質性チェック ---


def _make_vm_with_details(name="vm-1", pack_type="cpu", pack_num=4, disk_count=1):
    from mdx_cli.models.vm import VM
    extra_data = {
        "pack_type": pack_type,
        "pack_num": pack_num,
        "hard_disks": [
            {"disk_number": i + 1, "device_key": 2000 + i, "capacity": "40 GB"}
            for i in range(disk_count)
        ],
    }
    return VM.model_validate({
        "uuid": f"uuid-{name}",
        "name": name,
        "status": "PowerON",
        "service_level": "スポット仮想マシン",
        **extra_data,
    })


def test_check_reconfigure_homogeneity_uniform_ok():
    """全VMが同じpack_type・同じディスク数なら OK。"""
    from mdx_cli.commands.vm import _check_reconfigure_homogeneity
    vms = [
        _make_vm_with_details("vm-1", pack_type="cpu", disk_count=2),
        _make_vm_with_details("vm-2", pack_type="cpu", disk_count=2),
        _make_vm_with_details("vm-3", pack_type="cpu", disk_count=2),
    ]
    _check_reconfigure_homogeneity(vms)  # 例外が出なければOK


def test_check_reconfigure_homogeneity_pack_type_mismatch():
    """pack_type が混在したら typer.Exit。"""
    import typer
    import pytest
    from mdx_cli.commands.vm import _check_reconfigure_homogeneity
    vms = [
        _make_vm_with_details("vm-1", pack_type="cpu"),
        _make_vm_with_details("vm-2", pack_type="gpu"),
    ]
    with pytest.raises(typer.Exit):
        _check_reconfigure_homogeneity(vms)


def test_check_reconfigure_homogeneity_disk_count_mismatch():
    """ディスク本数が混在したら typer.Exit。"""
    import typer
    import pytest
    from mdx_cli.commands.vm import _check_reconfigure_homogeneity
    vms = [
        _make_vm_with_details("vm-1", disk_count=1),
        _make_vm_with_details("vm-2", disk_count=2),
    ]
    with pytest.raises(typer.Exit):
        _check_reconfigure_homogeneity(vms)


def test_vm_reconfigure_all_details_failed_exits():
    """詳細取得が全て失敗したら typer.Exit(1) で抜ける（IndexError 防止）。"""
    vms_brief = [
        _make_vm("worker-0", "uuid-0"),
        _make_vm("worker-1", "uuid-1"),
    ]
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=vms_brief):
        with patch("mdx_cli.commands.vm._fetch_vm_details", return_value=[]):
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                    result = runner.invoke(app, [
                        "reconfigure", "worker-*", "-p", "proj-1", "--no-wait",
                    ])
                    assert result.exit_code == 1
                    assert "構成変更可能なVMがありません" in result.output


def test_vm_reconfigure_pattern_matches_multiple_vms():
    """パターン指定で複数台マッチ → _parallel_vm_action で一括reconfigure。"""
    vms_brief = [
        _make_vm("worker-0", "uuid-0", status="PowerOFF"),
        _make_vm("worker-1", "uuid-1", status="PowerOFF"),
        _make_vm("worker-2", "uuid-2", status="PowerOFF"),
    ]
    vms_detail = [
        _make_vm_with_details("worker-0", pack_type="cpu", pack_num=4, disk_count=1),
        _make_vm_with_details("worker-1", pack_type="cpu", pack_num=4, disk_count=1),
        _make_vm_with_details("worker-2", pack_type="cpu", pack_num=4, disk_count=1),
    ]
    # 詳細取得時に status を PowerOFF に（稼働中処理を回避）
    for v in vms_detail:
        v.status = "PowerOFF"

    with patch("mdx_cli.commands.vm._resolve_vms", return_value=vms_brief):
        with patch("mdx_cli.commands.vm._fetch_vm_details", return_value=vms_detail):
            with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
                with patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[
                    {"task_id": "task-0"}, {"task_id": "task-1"}, {"task_id": "task-2"}
                ]) as mock_action:
                    with patch("mdx_cli.commands.vm.get_client"):
                        with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                            with patch("mdx_cli.commands.vm.questionary") as mock_q:
                                mock_q.text.return_value.unsafe_ask.side_effect = ["8", "40"]
                                mock_q.confirm.return_value.unsafe_ask.return_value = True
                                result = runner.invoke(app, [
                                    "reconfigure", "worker-*",
                                    "-p", "proj-1", "--no-wait",
                                ])
                                assert result.exit_code == 0, result.output
                                mock_action.assert_called_once()
                                # action_name は "構成変更中"
                                args = mock_action.call_args
                                assert args[0][2] == "構成変更中"


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


# --- バルク操作のトークン事前リフレッシュ ---


def test_parallel_vm_action_refreshes_token_before_bulk():
    """バルク操作の前に事前リフレッシュが呼ばれる。"""
    vm = _make_vm()
    with patch("mdx_cli.commands.vm.refresh_token_proactive") as mock_refresh:
        with patch("mdx_cli.commands.vm.parallel_post", return_value=[{}]):
            with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
                from mdx_cli.commands.vm import _parallel_vm_action
                _parallel_vm_action([vm], lambda v: f"/api/vm/{v.uuid}/stop/", "停止中")
                mock_refresh.assert_called_once()


def test_parallel_vm_action_refreshes_once_for_small_batch():
    """30台以下のバルク操作はリフレッシュ1回だけ。"""
    vms = [_make_vm(f"vm-{i}", f"uuid-{i}") for i in range(30)]
    with patch("mdx_cli.commands.vm.refresh_token_proactive") as mock_refresh:
        with patch("mdx_cli.commands.vm.parallel_post", return_value=[{}] * 30):
            with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
                from mdx_cli.commands.vm import _parallel_vm_action
                _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/stop/", "停止中")
                assert mock_refresh.call_count == 1


def test_parallel_vm_action_refreshes_per_chunk_for_large_batch():
    """31台以上のバルク操作は30台ごとにリフレッシュ。"""
    vms = [_make_vm(f"vm-{i}", f"uuid-{i}") for i in range(75)]

    with patch("mdx_cli.commands.vm.refresh_token_proactive") as mock_refresh:
        with patch("mdx_cli.commands.vm.parallel_post") as mock_post:
            mock_post.side_effect = [
                [{}] * 30,
                [{}] * 30,
                [{}] * 15,
            ]
            with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
                from mdx_cli.commands.vm import _parallel_vm_action
                results = _parallel_vm_action(vms, lambda v: f"/api/vm/{v.uuid}/stop/", "停止中")
                # 75 / 30 = 3 チャンク（30, 30, 15）→ refresh 3回
                assert mock_refresh.call_count == 3
                assert mock_post.call_count == 3
                assert len(results) == 75


# --- deploy コマンド ---




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


# --- SSH公開鍵 一覧/警告 ---



def test_list_pubkeys_orders_standard_keys_first(tmp_path):
    """~/.ssh の *.pub を、標準鍵名を優先しつつ列挙する。"""
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    for name in ["zzz.pub", "aaa.pub", "id_rsa.pub", "id_ed25519.pub"]:
        (ssh_dir / name).write_text("ssh-key")
    # .pub でないものは除外される
    (ssh_dir / "id_rsa").write_text("private")
    (ssh_dir / "config").write_text("config")

    with patch.object(Path, "home", return_value=tmp_path):
        result = _list_pubkeys()

    assert [p.name for p in result] == [
        "id_ed25519.pub",
        "id_rsa.pub",
        "aaa.pub",
        "zzz.pub",
    ]


def test_list_pubkeys_returns_empty_when_no_ssh_dir(tmp_path):
    """~/.ssh が無ければ空リストを返す。"""
    with patch.object(Path, "home", return_value=tmp_path):
        assert _list_pubkeys() == []




def test_pubkey_preview_abbreviates_long_content(tmp_path):
    """長い公開鍵は 先頭30文字...末尾30文字 に省略する。"""
    f = tmp_path / "k.pub"
    content = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYDATA0123456789ABCDEF "
        "user@example.com"
    )
    f.write_text(content + "\n")
    assert _pubkey_preview(f) == f"{content[:30]}...{content[-30:]}"


def test_pubkey_preview_short_content_shown_as_is(tmp_path):
    """短い内容（63文字以下）はそのまま返す。"""
    f = tmp_path / "k.pub"
    f.write_text("ssh-rsa SHORT")
    assert _pubkey_preview(f) == "ssh-rsa SHORT"


def _deploy_common_args(key_omitted=True):
    args = [
        "deploy",
        "-t", "Ubuntu",
        "-n", "test-{0-9}",
        "--pack-type", "cpu",
        "--pack-num", "4",
        "--disk", "40",
        "--service-level", "spot",
        "-y",
        "--no-wait",
    ]
    return args


def test_vm_deploy_interactive_lists_pubkeys_and_selects_by_number(tmp_path):
    """対話時、~/.ssh の .pub 一覧を表示し、番号入力で選択＋確認メッセージを出す。"""
    body3 = (
        "ssh-ed25519 AAAADATASETKEY3DATA0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ "
        "c@example.com"
    )
    keys = []
    for name, body in [
        ("id_ed25519.pub", "ssh-ed25519 AAAAEDKEY1DATA0000000000000000000 a@example.com"),
        ("mdx-aida-master.pub", "ssh-ed25519 AAAAMASTERKEY2DATA000000000000 b@example.com"),
        ("mdx-dataset-acc.pub", body3),
    ]:
        f = tmp_path / name
        f.write_text(body)
        keys.append(f)

    captured_requests: list = []

    def mock_deploy(client, req):
        captured_requests.append(req)
        return VMDeployResponse(task_id=[f"task-{i}" for i in range(10)])

    with patch("mdx_cli.commands.vm.list_templates", return_value=[_make_template()]):
        with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
            with patch("mdx_cli.commands.vm.deploy_vm", side_effect=mock_deploy):
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                        with patch("mdx_cli.commands.vm._list_pubkeys", return_value=keys):
                            with patch("mdx_cli.commands.vm.questionary") as mock_q:
                                mock_q.text.return_value.unsafe_ask.return_value = "3"
                                result = runner.invoke(app, _deploy_common_args())

    assert result.exit_code == 0, result.output
    assert "mdx-dataset-acc.pub" in result.output
    # 一覧に内容プレビュー（先頭30...末尾30）が出る
    assert f"{body3[:30]}...{body3[-30:]}" in result.output
    # 番号選択後の確認メッセージ
    assert "選択" in result.output
    assert captured_requests[0].shared_key == body3


def test_vm_deploy_interactive_warns_when_no_pubkey(tmp_path):
    """対話時、~/.ssh に .pub が無ければ警告を出す。"""
    key_file = tmp_path / "mykey.pub"
    key_file.write_text("ssh-ed25519 AAAAKEY2")

    captured_requests: list = []

    def mock_deploy(client, req):
        captured_requests.append(req)
        return VMDeployResponse(task_id=[f"task-{i}" for i in range(10)])

    with patch("mdx_cli.commands.vm.list_templates", return_value=[_make_template()]):
        with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
            with patch("mdx_cli.commands.vm.deploy_vm", side_effect=mock_deploy):
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                        with patch("mdx_cli.commands.vm._list_pubkeys", return_value=[]):
                            with patch("mdx_cli.commands.vm.questionary") as mock_q:
                                mock_q.text.return_value.unsafe_ask.return_value = str(key_file)
                                result = runner.invoke(app, _deploy_common_args())

    assert result.exit_code == 0, result.output
    assert "警告" in result.output
    assert ".pub" in result.output
    assert captured_requests[0].shared_key == "ssh-ed25519 AAAAKEY2"
