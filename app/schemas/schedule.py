import datetime

from pydantic import BaseModel

from app.abc.schedule_type import ScheduleType
from app.database import models


class Schedule(BaseModel):
    date: datetime.date
    type: ScheduleType

    @classmethod
    def create(cls, schedule: "models.Schedule") -> "Schedule":
        return cls(
            date=schedule.date,
            type=schedule.type,
        )


class ScheduleOperationalResult(BaseModel):
    result: bool
    date: datetime.date
