import datetime

from pydantic import BaseModel

from app.database import models
from app.schemas import Member


class Session(BaseModel):
    token: str
    member_id: int
    created_at: datetime.datetime
    member: Member

    class Config:
        from_attributes = True
