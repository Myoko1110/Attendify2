import datetime

from pydantic import BaseModel

from app.abc.schedule_type import ScheduleType
from app.database import models


class Schedule(BaseModel):
    date: datetime.date
    type: ScheduleType
    generations: list[int] | None = None
    groups: list[str] | None = None
    exclude_groups: list[str] | None = None

    class Config:
        from_attributes = True


class ScheduleOperationalResult(BaseModel):
    result: bool
    date: datetime.date
