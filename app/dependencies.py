from starlette.requests import Request

from app.abc.api_error import APIErrorCode
from app.database import db


async def get_valid_session(request: Request):

    token = request.session.get("token")
    if token:
        session = await db.get_session_by_valid_token(token)
        if session:
            return session

    raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Invalid authentication credentials", 401)
