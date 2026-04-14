from datetime import datetime

from pydantic import BaseModel


class TokenPair(BaseModel):
    token: str
    expires_at: datetime | None = None
