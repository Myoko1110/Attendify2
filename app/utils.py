import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from app import schemas
from app.schemas import Member


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


JST = ZoneInfo("Asia/Tokyo")


class Month:
    def __init__(self, year: int, month: int):
        self.year = year
        self.month = month  # 1-12

    def __eq__(self, other):
        if isinstance(other, Month):
            return self.year == other.year and self.month == other.month
        return False

    def __hash__(self):
        return hash((self.year, self.month))

    def __str__(self):
        return f"{self.year:04d}-{self.month:02d}"

    @classmethod
    def from_string(cls, value: str) -> "Month":
        parts = value.split("-")
        return cls(int(parts[0]), int(parts[1]))

    @classmethod
    def from_date(cls, date: datetime.date) -> "Month":
        return cls(date.year, date.month)


class Attendances(list[schemas.Attendance]):
    def __init__(self, *args):
        super().__init__(args)

    def calc(self, actual: bool = False) -> float | None:
        if not self:
            return None

        scores = actual_attendance_score if actual else attendance_score

        total = 0
        score = 0

        for attendance in self:
            if attendance.attendance in scores:
                s = scores[attendance.attendance]
                if s is not None:
                    total += 1
                    score += s
            else:
                if actual:
                    total += 1

        if total == 0:
            return None

        return float(
            (Decimal(str(score)) / Decimal(str(total)))
            .quantize(Decimal("0.1"), rounding="ROUND_HALF_UP")
        )

    def filter_by_part(self, part: schemas.Part) -> "Attendances":
        return Attendances(*[a for a in self if a.member and a.member.part == part])

    def filter_by_member(self, member: Member) -> "Attendances":
        return Attendances(*[a for a in self if a.member and a.member.id == member.id])

    def filter_by_date(self, date: datetime.date) -> "Attendances":
        return Attendances(*[a for a in self if a.date == date])


def determine_attendance_status_utc(
        now_utc: datetime.datetime,
        start_time: datetime.time,
        end_time: datetime.time,
        buffer_min: int = 0,
        existing_status: str = None
) -> str:
    """
    DBの時刻(JST/naive)をJSTとして解釈し、UTCの現在時刻と比較します。
    """
    # 1. 現在時刻をJSTに変換（比較をJSTで統一するため）
    now_jst = now_utc.astimezone(JST)
    today_jst = now_jst.date()

    # 2. DBのnaiveな時刻を「JSTのawareなdatetime」として組み立てる
    # .replace(tzinfo=JST) を使うことで、JSTとして扱われる
    start_dt_jst = datetime.datetime.combine(today_jst, start_time).replace(tzinfo=JST) + datetime.timedelta(minutes=buffer_min)
    end_dt_jst = datetime.datetime.combine(today_jst, end_time).replace(tzinfo=JST) - datetime.timedelta(minutes=buffer_min)

    # 3. JST同士で比較（これならズレもTypeErrorも起きません）
    is_late = now_jst > start_dt_jst
    is_early = now_jst < end_dt_jst

    # --- 以下、ステータス決定ロジック ---
    if existing_status is None:
        return "遅刻" if is_late else "出席"

    was_late = "遅刻" in existing_status
    if was_late and is_early: return "遅早"
    if was_late: return "遅刻"
    if is_early: return "早退"
    return "出席"


attendance_score = {
    '出席': 100,
    '欠席': 0,
    '講習': None,
    '遅刻': 50,
    '早退': 50,
    '無欠': 0,
}

actual_attendance_score = {
    '出席': 100,
    '欠席': 0,
    '講習': 0,
    '遅刻': 50,
    '早退': 50,
    '無欠': 0,
}


def load_setting_data():
    yaml_path = Path("settings.yml")
    with yaml_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_setting_data(data):
    yaml_path = Path("settings.yml")
    with yaml_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


settings = load_setting_data()
