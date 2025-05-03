from fastapi import APIRouter, Depends, Form
from google_auth_oauthlib.flow import Flow
from starlette.requests import Request

from app.abc.api_error import APIErrorCode
from app.database import db
from app.dependencies import get_valid_session
from app.schemas import Member

router = APIRouter(tags=["Authentication"])

REDIRECT_URI = "http://localhost:3039/login"

flow = Flow.from_client_secrets_file(
    "client_secret.json",
    scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    redirect_uri=REDIRECT_URI
)


@router.post(
    "/login",
    summary="ログイン",
    description="Googleアカウントでログインします。",
)
async def login(request: Request, code: str = Form(), state: str = Form()) -> Member:
    if request.session.get("state") != state:
        raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Authentication failed", 400)

    try:
        flow.fetch_token(code=code)

        session = flow.authorized_session()
        email = session.get("https://www.googleapis.com/userinfo/v2/me").json()

    except Exception as e:
        print(e)
        raise APIErrorCode.INVALID_AUTHENTICATION_CREDENTIALS.of("Authentication failed", 400)

    member = await db.get_member_by_email(email["email"])
    if not member:
        raise APIErrorCode.PERMISSION_DENIED.of("Permission denied", 403)

    # TODO: roleで権限を絞る

    token = await db.create_session(member)
    request.session["token"] = token
    request.session.pop("state")

    return member


@router.get(
    "/logout",
    summary="ログアウト",
    description="ログアウトします。",
    dependencies=[Depends(get_valid_session)]
)
async def logout(request: Request):
    token = request.session.get("token")
    if token:
        await db.remove_session(token)

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
