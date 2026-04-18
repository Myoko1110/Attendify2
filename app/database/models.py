from enum import Enum
from typing import Optional
from uuid import uuid4

import nanoid
from sqlalchemy import Boolean, Column, Date, DateTime, Double, ForeignKey, Integer, JSON, String, \
    TypeDecorator, UniqueConstraint, Uuid, Time
from sqlalchemy.orm import declarative_base, relationship

from app import utils
from app.abc.part import Part
from app.abc.role import Role
from app.abc.schedule_type import ScheduleType

Base = declarative_base()


def generate_nanoid():
    return nanoid.generate(size=10, alphabet="0123456789abcdefghijklmnopqrstuvwxyz")


class EnumType(TypeDecorator):
    impl = String

    def __init__(self, *args, **kwargs):
        self.enum_class = kwargs.pop('enum_class')
        TypeDecorator.__init__(self, *args, **kwargs)

    def process_bind_param(self, value: Enum, dialect):
        if value is not None:
            if not isinstance(value, self.enum_class):
                raise TypeError("Value should %s type" % self.enum_class)
            return value.value

    def process_result_value(self, value, dialect) -> Optional[Enum]:
        if value is not None:
            if not isinstance(value, str):
                raise TypeError("Value should have str type")
            return self.enum_class(value)
        return None


class Member(Base):
    __tablename__ = "members"

    id = Column(Uuid, primary_key=True, default=uuid4)

    part = Column(EnumType(enum_class=Part), nullable=False)
    generation = Column(Integer, nullable=False)
    name = Column(String(64), nullable=False)
    name_kana = Column(String(64), nullable=False)
    email = Column(String(64), unique=True, nullable=True)
    role = Column(EnumType(enum_class=Role), nullable=True)
    studentid = Column(Integer, unique=True, nullable=True)

    lecture_day = Column(JSON, nullable=False, default=[])
    is_competition_member = Column(Boolean, nullable=False, default=False)

    felica_idm = Column(String(23), nullable=True)

    groups = relationship("Group", secondary="member_groups", back_populates="members")
    weekly_participations = relationship("WeeklyParticipation", back_populates="member",
                                         cascade="all, delete-orphan", passive_deletes=True)
    membership_status_periods = relationship("MembershipStatusPeriod", back_populates="member",
                                             cascade="all, delete-orphan", passive_deletes=True)


class WeeklyParticipation(Base):
    __tablename__ = "weekly_participations"
    __table_args__ = (
        UniqueConstraint("member_id", "weekday"),
    )

    id = Column(Uuid, primary_key=True, default=uuid4)

    member_id = Column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=Mon ... 6=Sun

    default_attendance = Column(String(64), nullable=True)  # 出席入力画面の出席状態
    is_active = Column(Boolean, nullable=False, default=False)

    member = relationship("Member", back_populates="weekly_participations")


# 活動状態マスタ
class MembershipStatus(Base):
    __tablename__ = "membership_statuses"

    id = Column(Uuid, primary_key=True, default=uuid4)
    display_name = Column(String(64), nullable=False)

    is_attendance_target = Column(Boolean, nullable=False)  # 出席入力画面に表示するかどうか
    default_attendance = Column(String(32), nullable=False)  # 出席入力画面の出席状態
    is_pre_attendance_excluded = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=utils.now)

    status_periods = relationship("MembershipStatusPeriod", back_populates="status",
                                  cascade="all, delete-orphan", passive_deletes=True)


# 部員の状態期間
class MembershipStatusPeriod(Base):
    __tablename__ = "membership_status_periods"

    id = Column(Uuid, primary_key=True, default=uuid4)

    member_id = Column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    status_id = Column(Uuid, ForeignKey("membership_statuses.id", ondelete="CASCADE"),
                       nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utils.now)

    status = relationship("MembershipStatus", lazy="selectin")
    member = relationship("Member", back_populates="membership_status_periods")


# グループ
class Group(Base):
    __tablename__ = "groups"

    id = Column(Uuid, primary_key=True, default=uuid4)
    display_name = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utils.now)

    members = relationship("Member", secondary="member_groups", back_populates="groups")


class MemberGroup(Base):
    __tablename__ = "member_groups"
    __table_args__ = (
        UniqueConstraint("member_id", "group_id"),
    )

    member_id = Column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    group_id = Column(Uuid, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)

    member = relationship("Member", overlaps="groups,members")
    group = relationship("Group", overlaps="groups,members")


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("date", "member_id"),
    )

    id = Column(Uuid, nullable=False, primary_key=True, default=uuid4)
    date = Column(Date, nullable=False, index=True)
    member_id = Column(Uuid, ForeignKey("members.id", ondelete="SET NULL"), nullable=True)
    attendance = Column(String(64), nullable=False)

    first_tap_at = Column(DateTime(timezone=True), nullable=True)
    last_tap_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utils.now)
    updated_at = Column(DateTime(timezone=True), nullable=False, onupdate=utils.now,
                        default=utils.now)

    member = relationship("Member", lazy="select")


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Uuid, primary_key=True, default=uuid4)
    member_id = Column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)

    timestamp = Column(DateTime(timezone=True), nullable=False, default=utils.now)
    terminal_member_id = Column(Uuid, ForeignKey("members.id", ondelete="SET NULL"), nullable=False)

    member = relationship("Member", foreign_keys=[member_id], lazy="selectin")


class AttendanceRate(Base):
    __tablename__ = "attendance_rates"
    __table_args__ = (
        UniqueConstraint('target_id', 'month', 'actual'),
    )
    id = Column(Uuid, nullable=False, primary_key=True, default=uuid4)

    target_type = Column(String(16), nullable=False)  # 'member' | 'part' | 'all'
    target_id = Column(String(64), nullable=True)  # member_id | part_name | None

    month = Column(String(7), nullable=False)

    rate = Column(Double, nullable=True, default=None)
    actual = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utils.now,
                        onupdate=utils.now)


class Schedule(Base):
    __tablename__ = "schedules"

    date = Column(Date, nullable=False, primary_key=True)
    type = Column(EnumType(enum_class=ScheduleType), nullable=False)

    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    generations = Column(JSON, nullable=True)
    groups = Column(JSON, nullable=True)
    exclude_groups = Column(JSON, nullable=True)
    is_pre_attendance_target = Column(Boolean, nullable=False, default=True)


class PreAttendance(Base):
    __tablename__ = "pre_attendances"
    __table_args__ = (
        UniqueConstraint("date", "member_id"),
    )

    id = Column(Uuid, nullable=False, primary_key=True, default=uuid4)
    date = Column(Date, nullable=False, index=True)
    member_id = Column(Uuid, ForeignKey("members.id", ondelete="SET NULL"), nullable=True)
    attendance = Column(String(64), nullable=False)
    reason = Column(String(256), nullable=True)
    pre_check_id = Column(String(10), ForeignKey("pre_checks.id", ondelete="SET NULL"),
                          nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utils.now)
    updated_at = Column(DateTime(timezone=True), nullable=False, onupdate=utils.now,
                        default=utils.now)


class PreCheck(Base):
    __tablename__ = "pre_checks"

    id = Column(String(10), nullable=False, primary_key=True, default=generate_nanoid)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    description = Column(String(256), default="", nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    edit_deadline_days = Column(Integer, nullable=False, default=0)


class Session(Base):
    __tablename__ = "sessions"

    token = Column(String(512), primary_key=True)
    member_id = Column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utils.now)

    member = relationship("Member")


# ----------------------------
# RBAC models
# ----------------------------


class RBACPermission(Base):
    __tablename__ = "permissions"

    id = Column(Uuid, primary_key=True, default=uuid4)
    key = Column(String(128), nullable=False, unique=True)
    description = Column(String(256), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=utils.now)


class RBACRole(Base):
    __tablename__ = "roles"

    id = Column(Uuid, primary_key=True, default=uuid4)
    key = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(64), nullable=False)
    description = Column(String(256), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=utils.now)

    permissions = relationship(
        "RBACPermission",
        secondary="role_permissions",
        lazy="selectin",
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id"),
    )

    role_id = Column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class MemberRole(Base):
    __tablename__ = "member_roles"
    __table_args__ = (
        UniqueConstraint("member_id", "role_id"),
    )

    member_id = Column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class GenerationRole(Base):
    """Role assignments for a generation (=grade).

    This supports "assign a role to all members of a given generation".
    """

    __tablename__ = "generation_roles"
    __table_args__ = (
        UniqueConstraint("generation", "role_id"),
    )

    generation = Column(Integer, primary_key=True)
    role_id = Column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class PermissionImplies(Base):
    """Permission implication edges.

    If a principal has parent_permission, they implicitly have child_permission.
    """

    __tablename__ = "permission_implies"
    __table_args__ = (
        UniqueConstraint("parent_permission_id", "child_permission_id"),
    )

    parent_permission_id = Column(
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    child_permission_id = Column(
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

