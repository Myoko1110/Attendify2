from pydantic import BaseModel


class PartSchema(BaseModel):
    jp: str
    en: str
    en_short: str

    @classmethod
    def create(cls, detail):
        return cls(
            jp=detail.japanese,
            en=detail.english,
            en_short=detail.english_short
        )


class GradeSchema(BaseModel):
    generation: int
    display_name: str


class GradesSchema(BaseModel):
    senior2: GradeSchema
    senior1: GradeSchema
    junior3: GradeSchema
    junior2: GradeSchema
    junior1: GradeSchema
