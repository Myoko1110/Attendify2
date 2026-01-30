import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, Double, ForeignKey, Integer, JSON, String, \
    TypeDecorator, UniqueConstraint, Uuid
from sqlalchemy.orm import declarative_base, relationship

from app import utils
from app.abc.part import Part
from app.abc.role import Role
from app.abc.schedule_type import ScheduleType

Base = declarative_base()


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

    def process_result_value(self, value, dialect) -> Enum:
        if value is not None:
            if not isinstance(value, str):
                raise TypeError("Value should have str type")
            return self.enum_class(value)


class AwareDateTime(TypeDecorator):
    impl = String

    def process_bind_param(self, value: datetime.datetime, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timezone-aware datetime required.")
            return value.isoformat(timespec="seconds")
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return datetime.datetime.fromisoformat(value).astimezone(datetime.timezone.utc)
        return None


class Member(Base):
    __tablename__ = "members"
    __table_args__ = {
        "sqlite_autoincrement": True,
    }

    id = Column(Uuid, primary_key=True, default=uuid4)

    part = Column(EnumType(enum_class=Part), nullable=False)
    generation = Column(Integer, nullable=False)
    name = Column(String(64), nullable=False)
    name_kana = Column(String(64), nullable=False)
    email = Column(String(64), unique=True, nullable=True)
    role = Column(EnumType(enum_class=Role), nullable=True)

    lecture_day = Column(JSON, nullable=False, default=[])
    is_competition_member = Column(Boolean, nullable=False, default=False)
    is_temporarily_retired = Column(Boolean, nullable=False, default=False)

    groups = relationship("Group", secondary="member_groups", back_populates="members")
    weekly_participations = relationship("WeeklyParticipation", back_populates="member")
    membership_status_periods = relationship("MembershipStatusPeriod", back_populates="member")


class WeeklyParticipation(Base):
    __tablename__ = "weekly_participations"
    __table_args__ = (
        UniqueConstraint("member_id", "weekday"),
    )

    id = Column(Uuid, primary_key=True, default=uuid4)

    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
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

    created_at = Column(AwareDateTime, default=utils.now)


# 部員の状態期間
class MembershipStatusPeriod(Base):
    __tablename__ = "membership_status_periods"

    id = Column(Uuid, primary_key=True, default=uuid4)

    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
    status_id = Column(Uuid, ForeignKey("membership_statuses.id"), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    created_at = Column(AwareDateTime, default=utils.now)

    status = relationship("MembershipStatus", lazy="selectin")
    member = relationship("Member", back_populates="membership_status_periods")


# グループ
class Group(Base):
    __tablename__ = "groups"
    __table_args__ = {
        "sqlite_autoincrement": True,
    }

    id = Column(Uuid, primary_key=True, default=uuid4)
    display_name = Column(String(64), unique=True, nullable=False)
    created_at = Column(AwareDateTime, nullable=False, default=utils.now)

    members = relationship("Member", secondary="member_groups", back_populates="groups")


class MemberGroup(Base):
    __tablename__ = "member_groups"
    __table_args__ = (
        UniqueConstraint("member_id", "group_id"),
        {"sqlite_autoincrement": True},
    )

    member_id = Column(Uuid, ForeignKey("members.id"), primary_key=True)
    group_id = Column(Uuid, ForeignKey("groups.id"), primary_key=True)

    member = relationship("Member", overlaps="groups,members")
    group = relationship("Group", overlaps="groups,members")


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("date", "member_id"),
        {"sqlite_autoincrement": True},
    )

    id = Column(Uuid, nullable=False, primary_key=True, default=uuid4)
    date = Column(Date, nullable=False)
    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
    attendance = Column(String(64), nullable=False)
    created_at = Column(AwareDateTime, nullable=False, default=utils.now)
    updated_at = Column(AwareDateTime, nullable=False, onupdate=utils.now, default=utils.now)

    member = relationship("Member", lazy="selectin")


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
    updated_at = Column(AwareDateTime, nullable=False, default=utils.now, onupdate=utils.now)


class Schedule(Base):
    __tablename__ = "schedules"

    date = Column(Date, nullable=False, primary_key=True)
    type = Column(EnumType(enum_class=ScheduleType), nullable=False)
    generations = Column(JSON, nullable=True)
    groups = Column(JSON, nullable=True)
    exclude_groups = Column(JSON, nullable=True)


class ScheduleGroupRule(Base):
    __tablename__ = "schedule_group_rules"

    id = Column(Uuid, primary_key=True, default=uuid4)

    date = Column(Date, ForeignKey("schedules.date"), nullable=False)
    group_id = Column(Uuid, ForeignKey("groups.id"), nullable=False)

    rule = Column(String(16), nullable=False)
    # "only" | "exclude"


class Session(Base):
    __tablename__ = "sessions"

    token = Column(String(256), primary_key=True)
    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
    created_at = Column(AwareDateTime, nullable=False, default=utils.now)

    member = relationship("Member")
