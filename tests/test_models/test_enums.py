from mdx_cli.models.enums import ServiceLevel, TaskStatus, VMStatus


def test_vm_status_running():
    assert VMStatus.RUNNING == "Running"

def test_vm_status_stopped():
    assert VMStatus.STOPPED == "Stopped"

def test_service_level_spot():
    assert ServiceLevel.SPOT == "spot"

def test_service_level_guarantee():
    assert ServiceLevel.GUARANTEE == "guarantee"

def test_task_status_values():
    assert TaskStatus.RUNNING == "Running"
    assert TaskStatus.COMPLETED == "Completed"
    assert TaskStatus.FAILED == "Failed"
