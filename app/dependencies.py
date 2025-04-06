from starlette.requests import HTTPConnection

from app.abc.api_error import APIErrorCode
from app.database import db


async def get_valid_session(connection: HTTPConnection):
    try:
        token = connection.cookies["session"]
    except KeyError:
        pass
    else:
        session = await db.get_session_by_valid_token(token)
        if session:
            return session

    raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Invalid authentication credentials", 401)
