import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, JSON, String, \
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

    member = relationship("Member")


# class AttendanceRate(Base):
#     __tablename__ = "attendance_rates"
#     __table_args__ = (
#         UniqueConstraint('target_id', 'period_value', 'actual'),
#     )
#     id = Column(Uuid, nullable=False, primary_key=True, default=uuid4)
#
#     target_type = Column(String(16), nullable=False)  # 'member' | 'part' | 'all'
#     target_id = Column(String(64), nullable=True)  # member_id | part_name | None
#
#     period_type = Column(String(8), nullable=False)  # 'day' | 'month' | 'all'
#     period_value = Column(String(10), nullable=True)  # '2025-05' | '2025-05-12' | None
#
#     rate = Column(Double, nullable=True, default=None)
#     actual = Column(Boolean, nullable=False, default=False)
#     updated_at = Column(AwareDateTime, nullable=False, default=utils.now, onupdate=utils.now)


class Schedule(Base):
    __tablename__ = "schedules"

    date = Column(Date, nullable=False, primary_key=True)
    type = Column(EnumType(enum_class=ScheduleType), nullable=False)
    target = Column(JSON, nullable=True)  # ["junior1", "senior2", "competition"]


class Session(Base):
    __tablename__ = "sessions"

    token = Column(String(256), primary_key=True)
    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
    created_at = Column(AwareDateTime, nullable=False, default=utils.now)

    member = relationship("Member")
