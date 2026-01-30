import datetime
import typing
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.abc.part import Part
from app.abc.role import Role
from .membership_status import MembershipStatus


class GroupSummary(BaseModel):
    id: UUID
    display_name: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class Member(BaseModel):
    id: UUID
    part: Part
    generation: int
    name: str
    name_kana: str
    email: str | None
    role: Role
    lecture_day: list[str]
    is_competition_member: bool
    is_temporarily_retired: bool

    class Config:
        from_attributes = True


class MemberParams(BaseModel):
    part: Part
    generation: int
    name: str
    name_kana: str
    email: typing.Optional[str] = None
    role: Role
    lecture_day: list[str] = Field(default_factory=list)
    is_competition_member: bool = False
    is_temporarily_retired: bool = False


class MemberParamsOptional(BaseModel):
    part: Part | None = None
    generation: int | None = None
    name: str | None = None
    name_kana: str | None = None
    email: str | None = None
    role: Role | None = None
    lecture_day: list[str] | None = None
    is_competition_member: bool | None = None
    is_temporarily_retired: bool | None = None


class MemberOperationalResult(BaseModel):
    result: bool
    member_id: UUID | None


class MembersOperationalResult(BaseModel):
    result: bool


class WeeklyParticipation(BaseModel):
    id: UUID
    member_id: UUID
    weekday: int  # 0=Mon ... 6=Sun
    default_attendance: str | None
    is_active: bool

    class Config:
        from_attributes = True


class WeeklyParticipationParams(BaseModel):
    weekday: int  # 0=Mon ... 6=Sun
    default_attendance: str | None = None
    is_active: bool


class MembershipStatusPeriod(BaseModel):
    id: UUID
    member_id: UUID
    status_id: UUID
    start_date: datetime.date
    end_date: datetime.date | None
    created_at: datetime.datetime

    status: MembershipStatus

    class Config:
        from_attributes = True


class MembershipStatusPeriodParams(BaseModel):
    status_id: UUID
    start_date: datetime.date
    end_date: datetime.date | None


class MemberGroupsSchema(BaseModel):
    groups: list[GroupSummary] | None = None

    model_config = ConfigDict(from_attributes=True)


class MemberWeeklySchema(BaseModel):
    weekly_participations: list[WeeklyParticipation] | None = None

    model_config = ConfigDict(from_attributes=True)


class MembershipStatusPeriodSchema(BaseModel):
    membership_status_periods: list[MembershipStatusPeriod] | None = None

    model_config = ConfigDict(from_attributes=True)


class MemberDetailSchema(
    Member,
    MemberGroupsSchema,
    MemberWeeklySchema,
    MembershipStatusPeriodSchema,
):
    pass
