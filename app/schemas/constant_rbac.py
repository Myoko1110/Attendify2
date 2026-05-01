from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.constant import GradeSchema


class GradeWithRolesSchema(GradeSchema):
    generation_role_keys: list[str] = Field(default_factory=list)


class GradesWithRolesSchema(BaseModel):
    senior3: GradeWithRolesSchema
    senior2: GradeWithRolesSchema
    senior1: GradeWithRolesSchema
    junior3: GradeWithRolesSchema
    junior2: GradeWithRolesSchema
    junior1: GradeWithRolesSchema
