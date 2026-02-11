from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.database.models import Session


async def get_valid_session(request: Request, db: AsyncSession = Depends(get_db)) -> Session | None:
    token = request.session.get("token")
    if token:
        session = await cruds.get_session_by_valid_token(db, token)
        if session:
            return session

    raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Invalid authentication credentials", 401)
