import datetime

from pydantic import BaseModel

from app.abc.schedule_type import ScheduleType
from app.database import models


class Schedule(BaseModel):
    date: datetime.date
    type: ScheduleType
    target: list[str] | None = None

    @classmethod
    def create(cls, schedule: "models.Schedule") -> "Schedule":
        return cls(
            date=schedule.date,
            type=schedule.type,
            target=schedule.target,
        )


class ScheduleOperationalResult(BaseModel):
    result: bool
    date: datetime.date
