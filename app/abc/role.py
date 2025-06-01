from enum import Enum


class Role(Enum):
    EXECUTIVE = "exec"
    PART_LEADER = "part"
    ATTENDANCE_OFFICER = "officer"
    MEMBER = "member"

    UNKNOWN = "unk"

    @property
    def display_name(self) -> str:
        return ROLE_DISPLAY_NAME[self]

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


ROLE_DISPLAY_NAME = {
    Role.EXECUTIVE: "役員",
    Role.PART_LEADER: "パートリーダー",
    Role.ATTENDANCE_OFFICER: "出席係",
    Role.MEMBER: "部員",
    Role.UNKNOWN: "不明",
}
