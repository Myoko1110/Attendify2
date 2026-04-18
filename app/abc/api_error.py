from enum import IntEnum

from fastapi import HTTPException


class APIErrorCode(IntEnum):
    INVALID_AUTHENTICATION_CREDENTIALS = 100
    PERMISSION_DENIED = 101
    AUTHENTICATION_FAILED = 102

    ALREADY_EXISTS_ATTENDANCE = 200
    ALREADY_EXISTS_MEMBER_EMAIL = 201

    ROLE_NOT_FOUND = 300

    SCHEDULE_NOT_FOUND = 400
    INVALID_SCHEDULE = 401

    FELICA_NOT_FOUND = 500

    def of(self, detail: str, status_code: int = 400) -> "APIError":
        return APIError(self, detail, status_code)


class APIError(HTTPException):
    def __init__(self, code: APIErrorCode, detail: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
