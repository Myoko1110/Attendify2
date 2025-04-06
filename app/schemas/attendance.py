import datetime
from uuid import UUID

from pydantic import BaseModel

from app.database import models
from app.schemas.member import Member


class Attendance(BaseModel):
    id: UUID
    date: datetime.date
    attendance: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    member: Member

    @classmethod
    def create(cls, a: "models.Attendance") -> "Attendance":
        print(a)
        return cls(
            id=a.id,
            date=a.date,
            attendance=a.attendance,
            created_at=a.created_at,
            updated_at=a.updated_at,
            member=Member.create(a.member) if a.member else None,
        )


class AttendanceOperationalResult(BaseModel):
    result: bool
    attendance_id: UUID | None


class AttendancesOperationalResult(BaseModel):
    result: bool


class AttendancesParams(BaseModel):
    member_id: UUID
    attendance: str
    date: datetime.date
