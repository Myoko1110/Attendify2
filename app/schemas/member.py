from uuid import UUID

from pydantic import BaseModel

from app.abc.part import Part
from app.abc.role import Role
from app.database import models


class Member(BaseModel):
    id: UUID
    part: Part
    generation: int
    name: str
    name_kana: str
    email: str
    role: Role | None

    @classmethod
    def create(cls, m: "models.Member") -> "Member":
        return cls(
            id=m.id,
            part=m.part,
            generation=m.generation,
            name=m.name,
            name_kana=m.name_kana,
            email=m.email,
            role=m.role,
        )


class MemberParams(BaseModel):
    part: Part
    generation: int
    name: str
    name_kana: str
    email: str
    role: Role | None


class MemberParamsOptional(BaseModel):
    part: Part | None = None
    generation: int | None = None
    name: str | None = None
    name_kana: str | None = None
    email: str | None = None
    role: Role | None = None


class MemberOperationalResult(BaseModel):
    result: bool
    member_id: UUID | None


class MembersOperationalResult(BaseModel):
    result: bool
