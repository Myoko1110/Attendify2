import datetime

from pydantic import BaseModel

from app.abc.schedule_type import ScheduleType


class Schedule(BaseModel):
    date: datetime.date
    type: ScheduleType

    start_time: datetime.time | None
    end_time: datetime.time | None

    generations: list[int] | None = None
    groups: list[str] | None = None
    exclude_groups: list[str] | None = None
    is_pre_attendance_target: bool = False

    class Config:
        from_attributes = True


class ScheduleOperationalResult(BaseModel):
    result: bool
    date: datetime.date
