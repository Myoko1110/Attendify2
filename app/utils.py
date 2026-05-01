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
        details = []

        for attendance in self:
            if attendance.attendance in scores:
                s = scores[attendance.attendance]
                if s is not None:
                    total += 1
                    score += s
                    details.append(f"{attendance.attendance}={s}")
            else:
                if actual:
                    total += 1
                    details.append(f"{attendance.attendance}=unknown(counted)")

        if total == 0:
            return None

        result = float(
            (Decimal(str(score)) / Decimal(str(total)))
            .quantize(Decimal("0.1"), rounding="ROUND_HALF_UP")
        )

        import logging
        logging.debug(
            f"Attendances.calc(actual={actual}): "
            f"count={len(self)} score_sum={score} total={total} result={result}% "
            f"detail=[{','.join(details[:5])}{'...' if len(details) > 5 else ''}]"
        )

        return result

    def filter_by_part(self, part: schemas.Part) -> "Attendances":
        return Attendances(*[a for a in self if a.member and a.member.part == part])

    def filter_by_member(self, member: Member) -> "Attendances":
        return Attendances(*[a for a in self if a.member and a.member.id == member.id])

    def filter_by_date(self, date: datetime.date) -> "Attendances":
        return Attendances(*[a for a in self if a.date == date])


def determine_attendance_status_utc(
        now_jst: datetime.datetime,
        start_time: datetime.time,
        end_time: datetime.time,
        buffer_min: int = 0,
        first_tap_at: datetime.datetime | None = None,
) -> str:
    """
    1回目のタップ時刻(first_tap_at)と現在時刻(now_jst)をJST基準で比較して、
    出席状態を決定する。

    仕様:
    - 1回目のみ: Attendance には保存せず、AttendanceLog に記録する
    - 2回目で Attendance を確定保存する
    - 1回目の時点で start/end の前後を見て、2回目で最終状態を判定する
    """
    start_dt_jst = datetime.datetime.combine(now_jst.date(), start_time).replace(tzinfo=JST) + datetime.timedelta(minutes=buffer_min)
    end_dt_jst = datetime.datetime.combine(now_jst.date(), end_time).replace(tzinfo=JST) - datetime.timedelta(minutes=buffer_min)

    is_before_start = now_jst < start_dt_jst
    is_after_end = now_jst > end_dt_jst

    if first_tap_at is None:
        if is_before_start:
            return "早退"
        if is_after_end:
            return "遅刻"
        return "出席"

    first_tap_jst = first_tap_at.astimezone(JST)
    first_is_before_start = first_tap_jst < start_dt_jst
    first_is_after_end = first_tap_jst > end_dt_jst

    if first_is_before_start and is_after_end:
        return "出席"
    if first_is_after_end and is_before_start:
        return "遅早"
    if first_is_before_start:
        return "早退"
    if first_is_after_end:
        return "遅刻"
    if is_before_start:
        return "早退"
    if is_after_end:
        return "遅刻"
    return "出席"


attendance_score = {
    '出席': 100,
    '欠席': 0,
    '講習': None,
    '遅刻': 50,
    '早退': 50,
    '遅早': 50,
    '無欠': 0,
}

actual_attendance_score = {
    '出席': 100,
    '欠席': 0,
    '講習': 0,
    '遅刻': 50,
    '早退': 50,
    '遅早': 50,
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
