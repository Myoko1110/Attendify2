import datetime
from uuid import UUID

from pydantic import BaseModel

from app.abc.attendance_log_type import AttendanceLogType
from app.schemas import Member


class AttendanceLog(BaseModel):
    id: UUID
    member_id: UUID
    timestamp: datetime.datetime
    terminal_member_id: UUID
    type: AttendanceLogType

    member: Member

    class Config:
        from_attributes = True


class AttendanceLogWithAttendance(AttendanceLog):
    attendance: str
