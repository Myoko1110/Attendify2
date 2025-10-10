from fastapi import APIRouter, Depends, Form
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.dependencies import get_valid_session
from app.schemas import Member
from app.utils import settings

router = APIRouter(tags=["Authentication"])

flow = Flow.from_client_secrets_file(
    "client_secret.json",
    scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    redirect_uri=settings["REDIRECT_URI"]
)


@router.post(
    "/login",
    summary="ログイン",
    description="Googleアカウントでログインします。",
    response_model=Member,
)
async def login(request: Request, code: str = Form(), state: str = Form(), db: AsyncSession = Depends(get_db)):
    if request.session.get("state") != state:
        raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Authentication failed", 400)

    try:
        flow.fetch_token(code=code)

        session = flow.authorized_session()
        email = session.get("https://www.googleapis.com/userinfo/v2/me").json()

    except Exception as e:
        print(e)
        raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Authentication failed", 400)

    member = await cruds.get_member_by_email(db, email["email"])
    if not member:
        raise APIErrorCode.PERMISSION_DENIED.of("Permission denied", 403)

    # TODO: roleで権限を絞る

    token = await cruds.create_session(db, member)
    request.session["token"] = token
    request.session.pop("state")

    return member


@router.get(
    "/logout",
    summary="ログアウト",
    description="ログアウトします。",
    dependencies=[Depends(get_valid_session)]
)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.session.get("token")
    if token:
        await cruds.remove_session(db, token)

    request.session.pop("token")
    return dict(result=True)


@router.get(
    "/authorization_url",
    summary="Google認証URL",
    description="Google認証URLを取得します。",
)
async def get_authorization_url(request: Request):
    url, state = flow.authorization_url()
    request.session["state"] = state
    return dict(url=url, state=state)
