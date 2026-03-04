from uuid import UUID

from pydantic import BaseModel


class MembershipStatus(BaseModel):
    id: UUID
    display_name: str
    is_attendance_target: bool
    default_attendance: str
    is_pre_attendance_excluded: bool

    class Config:
        from_attributes = True


class MembershipStatusParams(BaseModel):
    display_name: str
    is_attendance_target: bool
    default_attendance: str
    is_pre_attendance_excluded: bool = False
