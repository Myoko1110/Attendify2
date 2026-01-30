import datetime
from uuid import UUID

from pydantic import BaseModel


class Group(BaseModel):
    id: UUID
    display_name: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True
