import datetime

from pydantic import BaseModel

from app.abc.schedule_type import ScheduleType
from app.database import models


class Schedule(BaseModel):
    date: datetime.date
    type: ScheduleType
    target: list[str] | None = None

    class Config:
        from_attributes = True


class ScheduleOperationalResult(BaseModel):
    result: bool
    date: datetime.date
