from enum import Enum


class Part(Enum):
    FLUTE = "flute"
    CLARINET = "clarinet"
    SAXOPHONE = "saxophone"
    DOUBLE_REED = "doublereed"
    TRUMPET = "trumpet"
    HORN = "horn"
    TROMBONE = "trombone"
    BASS = "bass"
    PERCUSSION = "percussion"

    @property
    def detail(self) -> "_Part":
        return PART_DETAIL[self]


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
}
