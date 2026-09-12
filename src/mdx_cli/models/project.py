from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Project(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str
    description: str = ""


class AssignedTenant(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    projects: list[Project]


class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str
    description: str = ""


class StorageInfo(BaseModel):
    model_config = ConfigDict(extra="allow")


class AccessKey(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str = ""


class ProjectResources(BaseModel):
    # 表示のみのフィールドは型を推測せず、APIの値を保持する。
    model_config = ConfigDict(extra="allow")


class ProjectUser(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    username: str


class ProjectUsers(BaseModel):
    model_config = ConfigDict(extra="allow")
    count: int
    results: list[ProjectUser]


class ProjectPoint(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProjectPoints(BaseModel):
    model_config = ConfigDict(extra="allow")
    lastConsumed: str | None = None
    results: list[ProjectPoint]


class ResourceUsage(BaseModel):
    model_config = ConfigDict(extra="allow")
    html: str | None = None
    err_msg: str | None = None


class UsageTable(BaseModel):
    model_config = ConfigDict(extra="allow")
    caption: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class OverviewKind(StrEnum):
    all = "all"
    resource = "resource"
    resource_list = "resource_list"
    vm = "vm"
    spot_vm = "spot_vm"
    guarantee_vm = "guarantee_vm"


class ReportLanguage(StrEnum):
    jp = "jp"
    en = "en"
