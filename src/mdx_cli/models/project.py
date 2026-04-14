from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str
    description: str = ""


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
