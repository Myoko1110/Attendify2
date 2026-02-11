import datetime
from uuid import UUID

from pydantic import BaseModel


class Attendance(BaseModel):
    id: UUID
    date: datetime.date
    attendance: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    member_id: UUID | None

    class Config:
        from_attributes = True


class AttendanceOperationalResult(BaseModel):
    result: bool
    attendance_id: UUID | None


class AttendancesOperationalResult(BaseModel):
    result: bool


class AttendancesParams(BaseModel):
    member_id: UUID
    attendance: str
    date: datetime.date


class AttendanceRate(BaseModel):
    id: UUID
    target_type: str  # 'member' | 'part' | 'all'
    target_id: str | None  # member_id | part_name | None
    month: str
    rate: float | None
    actual: bool
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class AttendanceRateParams(BaseModel):
    target_type: str  # 'member' | 'part' | 'all'
    target_id: str | None  # member_id | part_name | None
    month: str
    rate: float | None
    actual: bool
