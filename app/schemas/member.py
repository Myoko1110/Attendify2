import typing
from uuid import UUID

from pydantic import BaseModel, Field

from app.abc.part import Part
from app.abc.role import Role


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


class MemberParamsOptional(BaseModel):
    part: Part | None = None
    generation: int | None = None
    name: str | None = None
    name_kana: str | None = None
    email: str | None = None
    role: Role | None = None
    lecture_day: list[str] | None = None
    is_competition_member: bool | None = None


class MemberOperationalResult(BaseModel):
    result: bool
    member_id: UUID | None


class MembersOperationalResult(BaseModel):
    result: bool
