from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, TypeDecorator, \
    UniqueConstraint, Uuid
from sqlalchemy.orm import declarative_base, relationship

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


class Member(Base):
    __tablename__ = "members"
    __table_args__ = {
        "sqlite_autoincrement": True,
    }

    id = Column(Uuid, primary_key=True)
    part = Column(EnumType(enum_class=Part), nullable=False)
    generation = Column(Integer, nullable=False)
    name = Column(String(64), nullable=False)
    name_kana = Column(String(64), nullable=False)
    email = Column(String(64), nullable=False)
    role = Column(EnumType(enum_class=Role), nullable=True)


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("date", "member_id"),
        {"sqlite_autoincrement": True},
    )

    id = Column(Uuid, primary_key=True, default=uuid4)
    date = Column(Date, nullable=False)
    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
    attendance = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    member = relationship("Member")


class Schedule(Base):
    __tablename__ = "schedules"

    date = Column(Date, nullable=False, primary_key=True)
    type = Column(EnumType(enum_class=ScheduleType), nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(256), primary_key=True)
    member_id = Column(Uuid, ForeignKey("members.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    member = relationship("Member")
