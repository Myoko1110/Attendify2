from enum import IntEnum

from fastapi import HTTPException


class APIErrorCode(IntEnum):
    ALREADY_EXISTS_ATTENDANCE = 100

    PERMISSION_DENIED = 200
    INVALID_GOOGLE_API_CODE = 201
    INVALID_AUTHENTICATION_CREDENTIALS = 202

    def of(self, detail: str, status_code: int = 400) -> "APIError":
        return APIError(self, detail, status_code)


class APIError(HTTPException):
    def __init__(self, code: APIErrorCode, detail: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
