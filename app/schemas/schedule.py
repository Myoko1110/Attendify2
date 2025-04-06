import datetime

from pydantic import BaseModel

from app.abc.schedule_type import ScheduleType


class Schedule(BaseModel):
    date: datetime.date
    type: ScheduleType
