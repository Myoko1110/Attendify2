from enum import Enum


class Part(Enum):
    FLUTE = "fl"
    CLARINET = "cl"
    SAXOPHONE = "sax"
    DOUBLE_REED = "wr"
    TRUMPET = "trp"
    HORN = "hrn"
    TROMBONE = "trb"
    BASS = "bass"
    PERCUSSION = "perc"

    UNKNOWN = "unk"


    @property
    def detail(self) -> "_Part":
        return PART_DETAIL[self]

    def _missing_(self, value):
        return self.UNKNOWN

    def __repr__(self):
        return f"<Part.{self.name}>"

    def __str__(self):
        return f"Part.{self.name}"


class _Part:
    def __init__(self, japanese: str, english: str, english_short: str):
        self.japanese = japanese
        self.english = english
        self.english_short = english_short


PART_DETAIL = {
    Part.FLUTE: _Part("フルート", "Flute", "Fl"),
    Part.CLARINET: _Part("クラリネット", "Clarinet", "Cl"),
    Part.SAXOPHONE: _Part("サクソフォン", "Saxophone", "Sax"),
    Part.DOUBLE_REED: _Part("ダブルリード", "Double Reed", "Wr"),
    Part.TRUMPET: _Part("トランペット", "Trumpet", "Tp"),
    Part.HORN: _Part("ホルン", "Horn", "Hrn"),
    Part.TROMBONE: _Part("トロンボーン", "Trombone", "Tb"),
    Part.BASS: _Part("バス", "Bass", "Bass"),
    Part.PERCUSSION: _Part("パーカッション", "Percussion", "Perc"),
    Part.UNKNOWN: _Part("不明", "Unknown", "-"),
}
