from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.database.models import Session
from app.services import rbac


async def get_valid_session(request: Request, db: AsyncSession = Depends(get_db)) -> Session | None:
    token = request.session.get("token")
    if token:
        session = await cruds.get_session_by_valid_token(db, token)
        if session:
            return session

    raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Invalid authentication credentials", 401)


def require_permission(permission_key: str):
    async def _dep(
        session: Session = Depends(get_valid_session),
        db: AsyncSession = Depends(get_db),
    ) -> Session:
        keys = await rbac.effective_permission_keys_for_member(db, session.member_id)
        if permission_key in keys:
            return session
        raise APIErrorCode.PERMISSION_DENIED.of("Permission denied", 403)

    return _dep
