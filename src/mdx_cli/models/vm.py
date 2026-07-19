from pydantic import BaseModel, ConfigDict, Field

from mdx_cli.models.enums import ServiceLevel


class VM(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str = ""  # 詳細APIでは含まれない
    name: str
    status: str  # "PowerON", "PowerOFF" 等、API固有の文字列
    service_level: str = ""  # "スポット仮想マシン" 等の日本語文字列

    # 詳細APIで返り、ロジックで参照する頻出フィールド（一覧APIには無い）。
    # 表示にしか使わないフィールドは引き続き model_extra から参照する。
    pack_type: str | None = None  # "cpu" / "gpu"
    pack_num: int | None = None
    host_name: str | None = None
    hard_disks: list[dict] = Field(default_factory=list)
    service_networks: list[dict] = Field(default_factory=list)
    storage_networks: list[dict] = Field(default_factory=list)


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
