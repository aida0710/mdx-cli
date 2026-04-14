from pydantic import BaseModel, ConfigDict

from mdx_cli.models.enums import ServiceLevel, VMStatus


class VM(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str = ""  # 詳細APIでは含まれない
    name: str
    status: str  # "PowerON", "PowerOFF" 等、API固有の文字列
    service_level: str = ""  # "スポット仮想マシン" 等の日本語文字列


class VMDeployRequest(BaseModel):
    catalog: str
    project: str
    vm_name: str
    disk_size: int = 40
    storage_network: str = "portgroup"
    pack_type: str = "cpu"
    pack_num: int = 3
    service_level: ServiceLevel = ServiceLevel.SPOT
    network_adapters: list[dict]
    shared_key: str
    power_on: bool = False
    os_type: str = "Linux"
    template_name: str
    nvlink: bool = False


class VMDeployResponse(BaseModel):
    task_id: list[str]
