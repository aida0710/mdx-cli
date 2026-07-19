from mdx_cli.models.vm import VM, VMDeployRequest, VMDeployResponse


def test_vm_from_api_response():
    """実際のAPIレスポンス形式でVMを作成できる"""
    data = {
        "uuid": "abc-123",
        "name": "test-vm",
        "status": "PowerON",
        "service_level": "スポット仮想マシン",
        "vcenter": "172.17.4.18",
        "force_stop": False,
        "allocation": False,
    }
    vm = VM.model_validate(data)
    assert vm.uuid == "abc-123"
    assert vm.name == "test-vm"
    assert vm.status == "PowerON"
    assert vm.service_level == "スポット仮想マシン"


def test_vm_allows_extra_fields():
    """未知フィールドがあってもエラーにならない"""
    data = {
        "uuid": "abc-123",
        "name": "test-vm",
        "status": "PowerOFF",
        "service_level": "",
        "unknown_field": "some_value",
    }
    vm = VM.model_validate(data)
    assert vm.uuid == "abc-123"


def test_vm_deploy_request_defaults():
    req = VMDeployRequest(
        catalog="cat-1",
        project="proj-1",
        vm_name="my-vm",
        network_adapters=[{"adapter_number": 1, "segment": "seg-1"}],
        shared_key="ssh-rsa AAAA...",
        template_name="ubuntu-22",
    )
    assert req.disk_size == 40
    assert req.pack_type == "cpu"
    assert req.pack_num == 3
    assert req.service_level.value == "spot"
    assert req.power_on is False
    assert req.nvlink is False


def test_vm_deploy_response():
    resp = VMDeployResponse.model_validate({"task_id": ["task-abc"]})
    assert resp.task_id == ["task-abc"]

def test_vm_promotes_detail_fields():
    """詳細APIで返る頻出フィールドは型付きフィールドとして参照できる"""
    data = {
        "name": "test-vm",
        "status": "PowerON",
        "pack_type": "gpu",
        "pack_num": 2,
        "host_name": "ubuntu-2204",
        "hard_disks": [{"disk_number": 1, "device_key": 2000, "capacity": "40 GB"}],
        "service_networks": [{"adapter_number": 1, "ipv4_address": ["10.15.0.1"]}],
        "storage_networks": [],
    }
    vm = VM.model_validate(data)
    assert vm.pack_type == "gpu"
    assert vm.pack_num == 2
    assert vm.host_name == "ubuntu-2204"
    assert vm.hard_disks[0]["capacity"] == "40 GB"
    assert vm.service_networks[0]["ipv4_address"] == ["10.15.0.1"]
    assert vm.storage_networks == []


def test_vm_detail_fields_default_when_absent():
    """一覧APIのように詳細フィールドが無くてもデフォルトで参照できる"""
    vm = VM.model_validate({"name": "test-vm", "status": "PowerOFF"})
    assert vm.pack_type is None
    assert vm.pack_num is None
    assert vm.host_name is None
    assert vm.hard_disks == []
    assert vm.service_networks == []
    assert vm.storage_networks == []
