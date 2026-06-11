import json
from unittest.mock import patch

from typer.testing import CliRunner

from mdx_cli.commands.network import app, _collect_segment_acls, _collect_vm_ip_maps
from mdx_cli.models.network import ACL, DNAT, Segment, SegmentSummary
from mdx_cli.models.vm import VM

runner = CliRunner()


def test_segment_list_json():
    segments = [Segment(uuid="seg-1", name="Segment 1")]
    with patch("mdx_cli.commands.network.list_segments", return_value=segments):
        with patch("mdx_cli.commands.network.get_client"):
            result = runner.invoke(app, ["segment", "list", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1


def test_ips_json():
    ips = ["203.0.113.10", "203.0.113.11"]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=ips):
        with patch("mdx_cli.commands.network.get_client"):
            result = runner.invoke(app, ["ips", "--project-id", "proj-1", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data == ["203.0.113.10", "203.0.113.11"]


def test_ips_table():
    ips = ["203.0.113.10", "203.0.113.11"]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=ips):
        with patch("mdx_cli.commands.network.get_client"):
            result = runner.invoke(app, ["ips", "--project-id", "proj-1"])
            assert result.exit_code == 0
            assert "203.0.113.10" in result.output
            assert "203.0.113.11" in result.output


def test_segment_show():
    summary = SegmentSummary(vlan_id=100, vni=10000, ip_range="192.168.1.0/24")
    with patch("mdx_cli.commands.network.resolve_segment_id", return_value="seg-1"):
        with patch("mdx_cli.commands.network.get_segment_summary", return_value=summary):
            with patch("mdx_cli.commands.network.get_client"):
                result = runner.invoke(app, ["segment", "show", "seg-1", "--project-id", "proj-1"])
                assert result.exit_code == 0
                assert "192.168.1.0/24" in result.output


def test_collect_vm_ip_maps_builds_maps():
    vms = [VM(uuid="vm-1", name="web-1", status="PowerON")]
    detail = {
        "service_networks": [
            {"global_ip": "203.0.113.10", "ipv4_address": ["10.15.0.5"]}
        ]
    }
    with patch("mdx_cli.commands.network.list_vms", return_value=vms), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[detail]), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        maps = _collect_vm_ip_maps(None, "proj-1", json_mode=True)
    assert maps.private_ip_to_vm == {"10.15.0.5": "web-1"}
    assert maps.global_ip_to_vm == {"203.0.113.10": "VM: web-1"}
    assert maps.partial_failure is False


def test_collect_vm_ip_maps_detects_partial_failure():
    vms = [VM(uuid="vm-1", name="web-1", status="PowerON")]
    with patch("mdx_cli.commands.network.list_vms", return_value=vms), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[RuntimeError("boom")]), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        maps = _collect_vm_ip_maps(None, "proj-1", json_mode=True)
    assert maps.partial_failure is True
    assert maps.private_ip_to_vm == {}


def test_collect_vm_ip_maps_uses_conservative_concurrency():
    """VM詳細取得は過負荷でタイムアウトしないよう低い並列数で行う。"""
    vms = [VM(uuid="vm-1", name="web-1", status="PowerON")]
    with patch("mdx_cli.commands.network.list_vms", return_value=vms), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[{}]) as mock_pg, \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        _collect_vm_ip_maps(None, "proj-1", json_mode=True)
    mc = mock_pg.call_args.kwargs.get("max_concurrent")
    assert mc is not None and mc <= 10, f"max_concurrent={mc} は過大（VM詳細APIが詰まる）"


def test_check_ip_table_output():
    """check-ip 表示の特性化テスト（リファクタ前の挙動を固定）"""
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=["203.0.113.22"]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=[
             DNAT(uuid="d-1", pool_address="203.0.113.10", segment="s", dst_address="10.15.0.5")
         ]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "203.0.113.11", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    assert "203.0.113.11" in result.output  # VM割当IP
    assert "203.0.113.10" in result.output  # DNAT IP
    assert "203.0.113.22" in result.output  # 未使用IP
    assert "web-1" in result.output


def test_check_ip_fix_deletes_orphan_dnat():
    """--fix で死んだVM宛DNATを削除する"""
    dnats = [
        DNAT(uuid="d-alive", pool_address="203.0.113.10", segment="s", dst_address="10.15.0.5"),
        DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99"),
    ]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "d-hole"


def test_check_ip_fix_suppressed_on_partial_failure():
    """VM詳細取得が一部失敗したら --fix を抑止する"""
    dnats = [
        DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99"),
    ]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[RuntimeError("boom")]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_not_called()
    assert "スキップ" in result.output


def test_check_ip_deletes_dnat_on_confirm():
    """--fix なし、確認に yes で穴DNATを削除する"""
    dnats = [DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "d-hole"


def test_check_ip_keeps_dnat_on_decline():
    """--fix なし、確認に no で削除しない"""
    dnats = [DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = False
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_not_called()
    mock_q.confirm.assert_called_once()


_ACL_BASE = {
    "uuid": "acl-x",
    "protocol": "TCP",
    "src_address": "0.0.0.0",
    "src_mask": "0.0.0.0",
    "src_port": "Any",
    "dst_address": "10.15.0.5",
    "dst_mask": "255.255.255.255",
    "dst_port": "22",
}


def _make_acl(**overrides):
    return ACL(**{**_ACL_BASE, **overrides})


def test_collect_segment_acls_parallel():
    segments = [Segment(uuid="seg-1", name="A"), Segment(uuid="seg-2", name="B")]
    raw = [
        {"results": [_ACL_BASE]},
        {"results": []},
    ]
    with patch("mdx_cli.commands.network.parallel_get", return_value=raw), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")):
        acl_lists = _collect_segment_acls(None, segments, json_mode=True)
    assert len(acl_lists) == 2
    assert len(acl_lists[0]) == 1
    assert acl_lists[0][0].uuid == "acl-x"
    assert acl_lists[1] == []


def test_check_acl_classifies_holes_alive_range():
    """穴・生存・範囲指定を分類して表示する"""
    acls = [
        _make_acl(uuid="acl-hole", dst_address="10.15.0.99", dst_mask="255.255.255.255"),
        _make_acl(uuid="acl-alive", dst_address="10.15.0.5", dst_mask="255.255.255.255"),
        _make_acl(uuid="acl-range", dst_address="10.15.0.0", dst_mask="255.255.0.0"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = False
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    assert "10.15.0.99" in result.output  # 穴
    assert "10.15.0.5" in result.output   # 生存
    assert "10.15.0.0" in result.output   # 範囲
    assert "穴" in result.output
    assert "web-1" in result.output       # 生存にVM名


def test_check_acl_excludes_non_internal_dst():
    """10.15. 以外の dst（Any・外部IP）は一覧に出さない"""
    acls = [
        _make_acl(uuid="acl-any", dst_address="0.0.0.0", dst_mask="0.0.0.0"),
        _make_acl(uuid="acl-ext", dst_address="8.8.8.8", dst_mask="255.255.255.255"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    assert "8.8.8.8" not in result.output


def test_check_acl_json():
    """--json で穴の status を出力する"""
    acls = [_make_acl(uuid="acl-hole", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["status"] == "hole"
    assert data[0]["acl_id"] == "acl-hole"


def test_check_acl_fix_deletes_holes():
    """--fix で穴ACLを削除する"""
    acls = [
        _make_acl(uuid="acl-hole", dst_address="10.15.0.99"),
        _make_acl(uuid="acl-alive", dst_address="10.15.0.5"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "acl-hole"


def test_check_acl_fix_suppressed_on_partial_failure():
    """VM詳細取得が一部失敗したら --fix を抑止する"""
    acls = [_make_acl(uuid="acl-hole", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[RuntimeError("boom")]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_not_called()
    assert "スキップ" in result.output


def test_check_acl_deletes_on_confirm():
    """--fix なし、確認に yes で穴ACLを削除する"""
    acls = [_make_acl(uuid="acl-hole", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = True
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "acl-hole"


def test_check_acl_keeps_on_decline():
    """--fix なし、確認に no で削除しない"""
    acls = [_make_acl(uuid="acl-hole", dst_address="10.15.0.99")]
    with patch("mdx_cli.commands.network.list_segments", return_value=[
             Segment(uuid="seg-1", name="seg-A")
         ]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"), \
         patch("mdx_cli.commands.network.questionary") as mock_q:
        mock_q.confirm.return_value.unsafe_ask.return_value = False
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_not_called()
    mock_q.confirm.assert_called_once()

def test_check_ip_json_fix_deletes_and_keeps_stdout_json():
    """--json --fix でも削除が実行され、stdout は有効なJSONのまま"""
    dnats = [
        DNAT(uuid="d-hole", pool_address="203.0.113.20", segment="s", dst_address="10.15.0.99"),
    ]
    with patch("mdx_cli.commands.network.list_assignable_ips", return_value=[]), \
         patch("mdx_cli.commands.network.list_dnats", return_value=dnats), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.delete_dnat") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-ip", "--project-id", "proj-1", "--json", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "d-hole"
    # stdout は有効なJSON（削除メッセージは stderr に出る）
    json.loads(result.stdout)


def test_check_acl_json_fix_deletes_holes():
    """--json --fix でも穴ACLの削除が実行され、stdout は有効なJSONのまま"""
    seg = Segment(uuid="seg-1", name="seg1")
    acls = [
        ACL(uuid="a-hole", protocol="TCP", src_address="0.0.0.0", src_mask="0",
            src_port="Any", dst_address="10.15.0.99", dst_mask="255.255.255.255",
            dst_port="22"),
    ]
    with patch("mdx_cli.commands.network.list_segments", return_value=[seg]), \
         patch("mdx_cli.commands.network._collect_segment_acls", return_value=[acls]), \
         patch("mdx_cli.commands.network.list_vms", return_value=[
             VM(uuid="vm-1", name="web-1", status="PowerON")
         ]), \
         patch("mdx_cli.commands.network.parallel_get", return_value=[
             {"service_networks": [{"global_ip": "", "ipv4_address": ["10.15.0.5"]}]}
         ]), \
         patch("mdx_cli.commands.network.delete_acl") as mock_delete, \
         patch("mdx_cli.commands.network.get_client"), \
         patch("mdx_cli.commands.network.get_auth_context", return_value=("tok", "https://oprpl.mdx.jp")), \
         patch("mdx_cli.commands.network.resolve_project_id", return_value="proj-1"):
        result = runner.invoke(app, ["check-acl", "--project-id", "proj-1", "--json", "--fix"])
    assert result.exit_code == 0, result.output
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == "a-hole"
    json.loads(result.stdout)
