from enum import StrEnum
from decimal import Decimal, InvalidOperation

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

    @property
    def total_remaining_points(self) -> Decimal | None:
        """全明細の残ポイント合計。不明な値があれば部分合計を返さない。"""
        total = Decimal("0.00")
        for point in self.results:
            try:
                remaining = Decimal(str(getattr(point, "remaining_points", None)))
            except InvalidOperation:
                return None
            if not remaining.is_finite():
                return None
            total += remaining
        return total


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
