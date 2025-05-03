from enum import Enum


class ScheduleType(Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    WEEKDAY = "weekday"
    ALLDAY = "allday"
    OTHER = "other"
