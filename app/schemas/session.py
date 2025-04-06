import datetime

from pydantic import BaseModel


class Session(BaseModel):
    id: str
    member_id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
