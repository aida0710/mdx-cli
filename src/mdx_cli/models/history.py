from pydantic import BaseModel, ConfigDict


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = ""
    start_datetime: str = ""
    end_datetime: str = ""
    status: str = ""
    user_name: str = ""
    object_name: str = ""
