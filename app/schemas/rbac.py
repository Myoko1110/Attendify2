from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PermissionSchema(BaseModel):
    id: UUID
    key: str
    description: str

    model_config = ConfigDict(from_attributes=True)


class PermissionCreate(BaseModel):
    key: str
    description: str = ""


class PermissionUpdate(BaseModel):
    description: str | None = None


class RoleSchema(BaseModel):
    id: UUID
    key: str
    display_name: str
    description: str

    class Config:
        from_attributes = True


class RoleDetailSchema(RoleSchema):
    permissions: list[PermissionSchema] = Field(default_factory=list)


class RoleCreate(BaseModel):
    key: str
    display_name: str
    description: str = ""


class RoleUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None


class RolePermissionAssign(BaseModel):
    permission_keys: list[str]


class MemberRoleAssign(BaseModel):
    role_keys: list[str]


class ResultSchema(BaseModel):
    result: bool = True


class MemberRolesSchema(BaseModel):
    member_id: UUID
    role_keys: list[str]


class GenerationRoleAssign(BaseModel):
    role_keys: list[str]


class GenerationRole(BaseModel):
    generation: int
    role_keys: list[str] = Field(default_factory=list)


class PermissionImpliesEdgeSchema(BaseModel):
    parent_key: str
    child_key: str


class DefaultRolePermissionsSchema(BaseModel):
    role_keys: list[str] = Field(default_factory=list)
