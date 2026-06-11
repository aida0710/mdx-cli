from mdx_cli.commands._deploy_plan import DeployPlan
from mdx_cli.models.template import Template


def _make_plan(name_pattern: str, **overrides) -> DeployPlan:
    template = Template(
        uuid="tmpl-1",
        name="Ubuntu 22.04",
        template_name="ubuntu-2204",
        os_type="Linux",
        lower_limit_disk=40,
    )
    defaults = dict(
        template=template,
        segment_uuid="seg-1",
        name_pattern=name_pattern,
        disk_size=40,
        pack_type="cpu",
        pack_num=4,
        service_level="spot",
        shared_key="ssh-rsa AAAA...",
        power_on=False,
    )
    defaults.update(overrides)
    return DeployPlan(**defaults)


def test_vm_names_expands_pattern():
    plan = _make_plan("test-{0-9}")
    assert len(plan.vm_names) == 10
    assert plan.vm_names[0] == "test-0"
    assert plan.vm_names[-1] == "test-9"


def test_to_requests_digit_range_aggregates_to_one_request():
    """{0-9} は [0-9] のAPI範囲記法1リクエストに集約される"""
    plan = _make_plan("test-{0-9}")
    requests = plan.to_requests("proj-1")
    assert len(requests) == 1
    assert requests[0].vm_name == "test-[0-9]"
    assert requests[0].project == "proj-1"
    assert requests[0].catalog == "tmpl-1"


def test_to_requests_alpha_with_digit_aggregates_per_alpha():
    """{a-c}-{0-9} は3リクエスト（各リクエストで10台）に集約される"""
    plan = _make_plan("worker-{a-c}-{0-9}")
    requests = plan.to_requests("proj-1")
    assert [r.vm_name for r in requests] == [
        "worker-a-[0-9]",
        "worker-b-[0-9]",
        "worker-c-[0-9]",
    ]


def test_to_requests_zero_padded_does_not_aggregate():
    """{00-09} はAPI非対応のため1台ずつ10リクエストになる"""
    plan = _make_plan("node-{00-09}")
    requests = plan.to_requests("proj-1")
    assert len(requests) == 10
    assert requests[0].vm_name == "node-00"
    assert requests[-1].vm_name == "node-09"


def test_to_requests_carries_all_plan_fields():
    plan = _make_plan(
        "single-vm",
        disk_size=80,
        pack_type="gpu",
        pack_num=2,
        service_level="guarantee",
        power_on=True,
    )
    (req,) = plan.to_requests("proj-9")
    assert req.disk_size == 80
    assert req.pack_type == "gpu"
    assert req.pack_num == 2
    assert req.service_level == "guarantee"
    assert req.power_on is True
    assert req.shared_key == "ssh-rsa AAAA..."
    assert req.network_adapters == [{"adapter_number": 1, "segment": "seg-1"}]
    assert req.template_name == "ubuntu-2204"
    assert req.os_type == "Linux"


def test_to_requests_falls_back_to_template_display_name():
    """template_name が無いテンプレートは表示名・os_type は Linux にフォールバック"""
    template = Template(uuid="tmpl-2", name="Custom Template", lower_limit_disk=40)
    plan = _make_plan("vm-1", template=template)
    (req,) = plan.to_requests("proj-1")
    assert req.template_name == "Custom Template"
    assert req.os_type == "Linux"
