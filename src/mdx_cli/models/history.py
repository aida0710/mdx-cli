from pydantic import BaseModel, ConfigDict, field_validator


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = ""
    start_datetime: str = ""
    end_datetime: str = ""
    status: str = ""
    user_name: str = ""
    object_name: str = ""

    @field_validator("type", "start_datetime", "end_datetime", "status", "user_name", "object_name", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return "" if v is None else v
