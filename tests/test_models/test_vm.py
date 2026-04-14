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
