import datetime
from uuid import UUID

from pydantic import BaseModel, validator
from psycopg2.extras import DateRange


class PreAttendance(BaseModel):
    id: UUID
    date: datetime.date
    member_id: UUID | None
    attendance: str
    reason: str | None
    pre_check_id: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class PreAttendanceParams(BaseModel):
    date: datetime.date
    member_id: UUID | None
    attendance: str
    reason: str | None = None
    pre_check_id: str | None


class PreCheck(BaseModel):
    id: str
    start_date: datetime.date
    end_date: datetime.date
    description: str
    edit_deadline_days: int

    class Config:
        from_attributes = True


class PreCheckParams(BaseModel):
    start_date: datetime.date
    end_date: datetime.date
    description: str
    edit_deadline_days: int

    class Config:
        from_attributes = True
