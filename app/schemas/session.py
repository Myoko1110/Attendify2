import datetime

from pydantic import BaseModel

from app.database import models
from app.schemas import Member


class Session(BaseModel):
    token: str
    member_id: int
    created_at: datetime.datetime
    member: Member

    @classmethod
    def create(cls, session: "models.Session") -> "Session":
        return cls(
            token=session.token,
            member_id=session.member_id,
            created_at=session.created_at,
            member=Member.create(session.member),
        )
