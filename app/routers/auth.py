from fastapi import APIRouter, Depends
from google_auth_oauthlib.flow import Flow
from starlette.requests import HTTPConnection
from starlette.responses import Response

from app.abc.api_error import APIErrorCode
from app.database import db
from app.dependencies import get_valid_session
from app.schemas import Member

router = APIRouter()

REDIRECT_URI = "http://localhost:3030/login"

flow = Flow.from_client_secrets_file(
    "client_secret.json",
    scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    redirect_uri=REDIRECT_URI
)


@router.get(
    "/login",
    summary="ログイン",
    description="Googleアカウントでログインします。",
)
async def login(response: Response, code: str) -> Member:
    flow.fetch_token(code=code)
    session = flow.authorized_session()
    email = session.get("https://www.googleapis.com/userinfo/v2/me").json()

    member = await db.get_member_by_email(email["email"])
    if not member:
        raise APIErrorCode.PERMISSION_DENIED.of("Permission denied", 403)

    s = await db.create_session(member)

    response.set_cookie(
        key="session",
        value=s.token,
        max_age=60 * 60 * 24 * 30,
    )
    return s.member


@router.get(
    "/logout",
    summary="ログアウト",
    description="ログアウトします。",
    dependencies=[Depends(get_valid_session)]
)
async def logout(response: Response, connection: HTTPConnection):
    session = connection.cookies.get("session")
    if session:
        await db.delete_session()
    response.delete_cookie("session")
    return dict(result=True)


@router.get(
    "/authorization_url",
    summary="Google認証URL",
    description="Google認証URLを取得します。",
)
async def get_authorization_url():
    return flow.authorization_url()[0]
