from pydantic import BaseModel, ConfigDict, computed_field

from mdx_cli.models.enums import TaskStatus


class Task(BaseModel):
    model_config = ConfigDict(extra="allow")
    uuid: str
    type: str
    object_uuid: str
    object_name: str
    start_datetime: str
    end_datetime: str | None
    status: TaskStatus
    progress: int

    @computed_field
    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
