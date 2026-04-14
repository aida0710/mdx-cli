from pydantic import BaseModel, ConfigDict


class Template(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    name: str
    template_name: str | None = ""
    os_type: str | None = ""
    os_name: str | None = ""
    os_version: str | None = ""
    gpu_required: bool = False
    lower_limit_disk: int = 40
    login_username: str | None = "mdxuser"
    description: str | None = ""
