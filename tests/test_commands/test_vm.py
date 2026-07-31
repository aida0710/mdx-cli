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


def test_vm_rename_single():
    vm = _make_vm("worker-0", "uuid-0", status="PowerOFF")
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=[vm]):
        with patch("mdx_cli.commands.vm.list_vms", return_value=[vm]):
            with patch(
                "mdx_cli.commands.vm.rename_vm", return_value="task-rename"
            ) as mock_rename:
                with patch(
                    "mdx_cli.commands.vm._parallel_task_wait",
                    return_value=[
                        {"object_name": vm.name, "status": "Completed"}
                    ],
                ):
                    with patch("mdx_cli.commands.vm.get_client"):
                        with patch(
                            "mdx_cli.commands.vm.resolve_project_id",
                            return_value="proj-1",
                        ):
                            result = runner.invoke(
                                app,
                                ["rename", vm.uuid, "worker-0-vpn", "-p", "proj-1"],
                            )

    assert result.exit_code == 0, result.output
    mock_rename.assert_called_once_with(mock_rename.call_args.args[0], vm.uuid, "worker-0-vpn")


def test_vm_rename_pattern_with_suffix():
    vms = [
        _make_vm("worker-0", "uuid-0", status="PowerOFF"),
        _make_vm("worker-1", "uuid-1", status="PowerOFF"),
    ]
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=vms):
        with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
            with patch(
                "mdx_cli.commands.vm._parallel_vm_action",
                return_value=[{"task_id": "task-0"}, {"task_id": "task-1"}],
            ) as mock_action:
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch(
                        "mdx_cli.commands.vm.resolve_project_id",
                        return_value="proj-1",
                    ):
                        with patch("mdx_cli.commands.vm.questionary") as mock_q:
                            mock_q.confirm.return_value.unsafe_ask.return_value = True
                            result = runner.invoke(
                                app,
                                [
                                    "rename",
                                    "worker-*",
                                    "--suffix",
                                    "-vpn",
                                    "-p",
                                    "proj-1",
                                    "--no-wait",
                                ],
                            )

    assert result.exit_code == 0, result.output
    action_args = mock_action.call_args.args
    assert action_args[1](vms[0]) == "/api/vm/uuid-0/rename/"
    assert mock_action.call_args.kwargs["json_fn"](vms[0]) == {
        "vm_name": "worker-0-vpn"
    }
    assert mock_action.call_args.kwargs["json_fn"](vms[1]) == {
        "vm_name": "worker-1-vpn"
    }


def test_vm_rename_rejects_bulk_new_name():
    vms = [_make_vm("worker-0", "uuid-0"), _make_vm("worker-1", "uuid-1")]
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=vms):
        with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
            with patch("mdx_cli.commands.vm.get_client"):
                with patch(
                    "mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"
                ):
                    result = runner.invoke(
                        app,
                        ["rename", "worker-*", "one-name", "-p", "proj-1"],
                    )

    assert result.exit_code == 1
    assert "複数VMの名前変更には --suffix" in result.output


def test_vm_rename_rejects_existing_name_collision():
    vm = _make_vm("worker-0", "uuid-0")
    existing = _make_vm("worker-0-vpn", "uuid-existing")
    with patch("mdx_cli.commands.vm._resolve_vms", return_value=[vm]):
        with patch("mdx_cli.commands.vm.list_vms", return_value=[vm, existing]):
            with patch("mdx_cli.commands.vm.rename_vm") as mock_rename:
                with patch("mdx_cli.commands.vm.get_client"):
                    with patch(
                        "mdx_cli.commands.vm.resolve_project_id",
                        return_value="proj-1",
                    ):
                        result = runner.invoke(
                            app,
                            ["rename", vm.uuid, existing.name, "-p", "proj-1"],
                        )

    assert result.exit_code == 1
    assert "既存VMと衝突" in result.output
    mock_rename.assert_not_called()


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
                            with patch("mdx_cli.commands._common.questionary") as mock_common_q:
                                # パック数・ディスクGB は prompt_int（_common）経由
                                mock_common_q.text.return_value.unsafe_ask.side_effect = ["8", "40"]
                                with patch("mdx_cli.commands.vm.questionary") as mock_q:
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


# --- _resolve_vm_uuid: UUID / 名前 / 一覧選択 の解決 ---


def test_resolve_vm_uuid_passes_through_uuid():
    """UUID指定はAPIを呼ばずそのまま返す"""
    from mdx_cli.commands.vm import _resolve_vm_uuid

    with patch("mdx_cli.commands.vm.list_vms") as mock_list:
        result = _resolve_vm_uuid(None, "00000000-0000-0000-0000-000000000001", None)

    assert result == "00000000-0000-0000-0000-000000000001"
    mock_list.assert_not_called()


def test_resolve_vm_uuid_by_name():
    """名前指定は一覧から一致するVMのUUIDを返す"""
    from mdx_cli.commands.vm import _resolve_vm_uuid

    vms = [_make_vm("web-1", "uuid-1"), _make_vm("web-2", "uuid-2")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
            result = _resolve_vm_uuid(None, "web-2", None)

    assert result == "uuid-2"


def test_resolve_vm_uuid_name_not_found_fails():
    """名前が見つからなければ終了コード1"""
    import pytest
    import typer

    from mdx_cli.commands.vm import _resolve_vm_uuid

    with patch("mdx_cli.commands.vm.list_vms", return_value=[_make_vm("web-1", "uuid-1")]):
        with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
            with pytest.raises(typer.Exit) as exc_info:
                _resolve_vm_uuid(None, "no-such-vm", None)

    assert exc_info.value.exit_code == 1


def test_resolve_vm_uuid_no_target_selects_from_list():
    """target省略時は一覧から選択する"""
    from mdx_cli.commands.vm import _resolve_vm_uuid

    vms = [_make_vm("web-1", "uuid-1"), _make_vm("web-2", "uuid-2")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
            with patch("mdx_cli.commands.vm.select_from_list", return_value=vms[1]) as mock_sel:
                result = _resolve_vm_uuid(None, None, None)

    assert result == "uuid-2"
    assert mock_sel.call_args.args[0] == vms


def test_resolve_vm_uuid_running_only_filters_selection():
    """running_only=True なら稼働中VMだけを選択肢に出す"""
    from mdx_cli.commands.vm import _resolve_vm_uuid

    vms = [_make_vm("on-1", "uuid-1"), _make_vm("off-1", "uuid-2", status="PowerOFF")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
            with patch("mdx_cli.commands.vm.select_from_list", return_value=vms[0]) as mock_sel:
                result = _resolve_vm_uuid(None, None, None, running_only=True)

    assert result == "uuid-1"
    assert [v.name for v in mock_sel.call_args.args[0]] == ["on-1"]


def test_resolve_vm_uuid_running_only_no_running_fails():
    """running_only=True で稼働中VMがなければ終了コード1"""
    import pytest
    import typer

    from mdx_cli.commands.vm import _resolve_vm_uuid

    vms = [_make_vm("off-1", "uuid-1", status="PowerOFF")]
    with patch("mdx_cli.commands.vm.list_vms", return_value=vms):
        with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
            with pytest.raises(typer.Exit) as exc_info:
                _resolve_vm_uuid(None, None, None, running_only=True)

    assert exc_info.value.exit_code == 1


# --- _wait_for_poweroff タイムアウト検出 ---


def test_wait_for_poweroff_returns_timed_out_vms():
    """max_polls までに停止しなかったVMを返す。"""
    import httpx
    import respx

    from mdx_cli.commands.vm import _wait_for_poweroff

    vms = [_make_vm("vm-on", "uuid-on"), _make_vm("vm-off", "uuid-off")]
    with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        with respx.mock(base_url="https://oprpl.mdx.jp") as router:
            router.get("/api/vm/uuid-on/").mock(
                return_value=httpx.Response(200, json={"status": "PowerON"})
            )
            router.get("/api/vm/uuid-off/").mock(
                return_value=httpx.Response(200, json={"status": "PowerOFF"})
            )
            still_running = _wait_for_poweroff(vms, poll_interval=0, max_polls=2)

    assert [v.name for v in still_running] == ["vm-on"]


def test_wait_for_poweroff_all_stopped_returns_empty():
    """全VMが停止すれば空リストを返す。"""
    import httpx
    import respx

    from mdx_cli.commands.vm import _wait_for_poweroff

    vms = [_make_vm("vm-off", "uuid-off", status="PowerON")]
    with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        with respx.mock(base_url="https://oprpl.mdx.jp") as router:
            router.get("/api/vm/uuid-off/").mock(
                return_value=httpx.Response(200, json={"status": "PowerOFF"})
            )
            still_running = _wait_for_poweroff(vms, poll_interval=0, max_polls=2)

    assert still_running == []


def test_wait_for_poweroff_survives_non_json_response():
    """サーバー負荷時の非JSONレスポンスでクラッシュしない。

    70台 destroy の停止待ち中に JSONDecodeError でコマンド全体が
    落ちたバグの回帰テスト。一時エラーは次の周期で再確認する。
    """
    import httpx
    import respx

    from mdx_cli.commands.vm import _wait_for_poweroff

    vms = [_make_vm("vm-1", "uuid-1")]
    with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        with respx.mock(base_url="https://oprpl.mdx.jp") as router:
            router.get("/api/vm/uuid-1/").mock(
                side_effect=[
                    httpx.Response(502, text="<html>Bad Gateway</html>"),
                    httpx.Response(200, json={"status": "PowerOFF"}),
                ]
            )
            still_running = _wait_for_poweroff(vms, poll_interval=0, max_polls=5)

    assert still_running == []


def test_wait_for_poweroff_uses_low_concurrency():
    """VM詳細APIは遅いため並列数を8に制限して呼び出す。"""
    from mdx_cli.commands.vm import _wait_for_poweroff

    vms = [_make_vm("vm-1", "uuid-1")]
    with patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        with patch("mdx_cli.commands.vm.parallel_poll", return_value=[True]) as mock_poll:
            _wait_for_poweroff(vms, poll_interval=0, max_polls=2)

    assert mock_poll.call_args.kwargs.get("max_concurrent") == 8


def test_ensure_stopped_aborts_on_decline_when_timeout():
    """停止を確認できなかったVMがあり、続行を拒否したら Abort。"""
    import typer
    import pytest

    from mdx_cli.commands.vm import _ensure_stopped

    vm = _make_vm("vm-on", "uuid-on")
    with patch("mdx_cli.commands.vm._wait_for_poweroff", return_value=[vm]):
        with patch("mdx_cli.commands.vm.questionary") as mock_q:
            mock_q.confirm.return_value.unsafe_ask.return_value = False
            with pytest.raises(typer.Abort):
                _ensure_stopped([vm])
            # 危険側に倒すため default=False で確認する
            assert mock_q.confirm.call_args.kwargs.get("default") is False


def test_ensure_stopped_no_timeout_no_confirm():
    """全台停止できたら確認なしで戻る。"""
    from mdx_cli.commands.vm import _ensure_stopped

    vm = _make_vm("vm-off", "uuid-off")
    with patch("mdx_cli.commands.vm._wait_for_poweroff", return_value=[]):
        with patch("mdx_cli.commands.vm.questionary") as mock_q:
            _ensure_stopped([vm])
            mock_q.confirm.assert_not_called()


def test_vm_deploy_pack_num_out_of_range_fails(tmp_path):
    """--pack-num が上限（cpu=152）を超えたらエラー終了。"""
    key_file = tmp_path / "id.pub"
    key_file.write_text("ssh-rsa AAAA...")

    with patch("mdx_cli.commands.vm.list_templates", return_value=[_make_template()]):
        with patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]):
            with patch("mdx_cli.commands.vm.get_client"):
                with patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"):
                    result = runner.invoke(app, [
                        "deploy", "-t", "Ubuntu", "-n", "test-vm",
                        "--pack-type", "cpu", "--pack-num", "200",
                        "--disk", "40", "--service-level", "spot",
                        "-k", str(key_file), "-y", "--no-wait",
                    ])
                    assert result.exit_code == 1
                    assert "1〜152" in result.output


# --- 対話フローのリグレッションテスト ---


def test_vm_deploy_interactive_template_selection(tmp_path):
    """-t 省略時はテンプレート一覧から番号選択できる。"""
    key_file = tmp_path / "id.pub"
    key_file.write_text("ssh-rsa AAAA...")

    templates = [
        _make_template(),
        Template(uuid="tmpl-2", name="Debian 12", template_name="debian-12",
                 os_type="Linux", lower_limit_disk=40),
    ]
    captured: list = []

    def mock_deploy(client, req):
        captured.append(req)
        return VMDeployResponse(task_id=["task-1"])

    with patch("mdx_cli.commands.vm.list_templates", return_value=templates), \
         patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]), \
         patch("mdx_cli.commands.vm.deploy_vm", side_effect=mock_deploy), \
         patch("mdx_cli.commands.vm.get_client"), \
         patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands._common.questionary") as mock_common_q:
        mock_common_q.text.return_value.unsafe_ask.return_value = "2"
        result = runner.invoke(app, [
            "deploy", "-n", "test-vm",
            "--pack-type", "cpu", "--pack-num", "4",
            "--disk", "40", "--service-level", "spot",
            "-k", str(key_file), "-y", "--no-wait",
        ])

    assert result.exit_code == 0, result.output
    assert "Debian 12" in result.output
    assert captured[0].catalog == "tmpl-2"


def test_vm_reconfigure_stops_running_vms_first():
    """稼働中VMがあれば確認のうえシャットダウン→停止待ち→構成変更の順に実行する。"""
    vms_brief = [_make_vm("worker-0", "uuid-0", status="PowerON")]
    vms_detail = [_make_vm_with_details("worker-0", pack_type="cpu", pack_num=4, disk_count=1)]

    with patch("mdx_cli.commands.vm._resolve_vms", return_value=vms_brief), \
         patch("mdx_cli.commands.vm._fetch_vm_details", return_value=vms_detail), \
         patch("mdx_cli.commands.vm.list_segments", return_value=[_make_segment()]), \
         patch("mdx_cli.commands.vm._parallel_vm_action", return_value=[{}]) as mock_action, \
         patch("mdx_cli.commands.vm._ensure_stopped") as mock_ensure, \
         patch("mdx_cli.commands.vm.reconfigure_vm", return_value="task-1"), \
         patch("mdx_cli.commands.vm.get_client"), \
         patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands._common.questionary") as mock_common_q, \
         patch("mdx_cli.commands.vm.questionary") as mock_q:
        mock_common_q.text.return_value.unsafe_ask.side_effect = ["8", "40"]
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["reconfigure", "worker-*", "-p", "proj-1", "--no-wait"])

    assert result.exit_code == 0, result.output
    # シャットダウンの一括実行 → 停止待ち の順で呼ばれる
    assert mock_action.call_args[0][2] == "シャットダウン中"
    mock_ensure.assert_called_once_with(vms_detail)


def _make_vm_with_network(name="web-1", uuid="uuid-net", host_name=None):
    data = {
        "uuid": uuid,
        "name": name,
        "status": "PowerON",
        "service_networks": [{
            "adapter_number": 1,
            "ipv4_address": ["10.15.0.7"],
            "global_ip": "203.0.113.7",
        }],
    }
    if host_name:
        data["host_name"] = host_name
    return VM.model_validate(data)


def test_vm_ssh_builds_command_with_private_ip():
    """名前指定でプライベートIPへのsshコマンドを組み立てて exec する。"""
    brief = _make_vm("web-1", "uuid-net")
    detail = _make_vm_with_network()

    with patch("mdx_cli.commands.vm.list_vms", return_value=[brief]), \
         patch("mdx_cli.commands.vm.get_vm", return_value=detail), \
         patch("mdx_cli.commands.vm.get_client"), \
         patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"), \
         patch("os.execvp") as mock_exec:
        result = runner.invoke(app, ["ssh", "web-1", "-p", "proj-1"])

    assert result.exit_code == 0, result.output
    mock_exec.assert_called_once_with("ssh", ["ssh", "mdxuser@10.15.0.7"])


def test_vm_ssh_uses_global_ip_with_flag():
    """--global 指定時はグローバルIPに接続する。"""
    brief = _make_vm("web-1", "uuid-net")
    detail = _make_vm_with_network()

    with patch("mdx_cli.commands.vm.list_vms", return_value=[brief]), \
         patch("mdx_cli.commands.vm.get_vm", return_value=detail), \
         patch("mdx_cli.commands.vm.get_client"), \
         patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"), \
         patch("os.execvp") as mock_exec:
        result = runner.invoke(app, ["ssh", "web-1", "-p", "proj-1", "--global"])

    assert result.exit_code == 0, result.output
    mock_exec.assert_called_once_with("ssh", ["ssh", "mdxuser@203.0.113.7"])


def test_vm_ssh_global_flag_without_global_ip_fails():
    """--global を明示したのに global_ip が無ければ、黙って内部IPに落とさず失敗する。

    グローバル経由で繋ぐ意図で指定しているので、静かに別経路へ繋ぐと
    「繋がったから通っている」と誤認させる。
    """
    brief = _make_vm("web-1", "uuid-net")
    detail = VM.model_validate({
        "uuid": "uuid-net",
        "name": "web-1",
        "status": "PowerON",
        "service_networks": [{
            "adapter_number": 1,
            "ipv4_address": ["10.15.0.7"],
            "global_ip": "",
        }],
    })

    with patch("mdx_cli.commands.vm.list_vms", return_value=[brief]), \
         patch("mdx_cli.commands.vm.get_vm", return_value=detail), \
         patch("mdx_cli.commands.vm.get_client"), \
         patch("mdx_cli.commands.vm.resolve_project_id", return_value="proj-1"), \
         patch("os.execvp") as mock_exec:
        result = runner.invoke(app, ["ssh", "web-1", "-p", "proj-1", "--global"])

    assert result.exit_code != 0
    mock_exec.assert_not_called()


def test_vm_csv_survives_partial_failure():
    """1台の取得に失敗しても残りはCSV出力し、失敗分を警告する。

    _fetch_vm_details と同じく部分失敗で全体を落とさない。
    """
    import httpx

    vms = [_make_vm("vm-a", "uuid-a"), _make_vm("vm-b", "uuid-b")]
    req = httpx.Request("GET", "https://oprpl.mdx.jp/api/vm/uuid-b/csv/")
    err = httpx.HTTPStatusError(
        "boom", request=req, response=httpx.Response(500, request=req)
    )

    with patch("mdx_cli.commands.vm.list_vms", return_value=vms), \
         patch("mdx_cli.commands.vm.get_client"), \
         patch("mdx_cli.commands.vm.parallel_get", return_value=[{"name": "vm-a"}, err]):
        result = runner.invoke(app, ["csv", "-p", "proj-1"])

    assert result.exit_code == 0, result.output
    assert "vm-a" in result.output
    assert "vm-b" in result.output


def test_fetch_vm_details_uses_vm_detail_concurrency():
    """VM詳細の並列取得は専用の低並列度を使う（/api/vm/{uuid}/ は遅い）。"""
    from mdx_cli.api.parallel import MAX_CONCURRENT_VM_DETAIL
    from mdx_cli.commands.vm import _fetch_vm_details

    vms = [_make_vm("a", "uuid-a"), _make_vm("b", "uuid-b")]
    details = [
        {"name": v.name, "status": v.status, "service_level": v.service_level}
        for v in vms
    ]
    with patch("mdx_cli.commands.vm.parallel_get", return_value=details) as mock_get, \
         patch("mdx_cli.commands.vm.get_auth_context", return_value=("tok", "url")):
        _fetch_vm_details(None, vms)

    assert mock_get.call_args.kwargs["max_concurrent"] == MAX_CONCURRENT_VM_DETAIL
