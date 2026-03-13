from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.abc.api_error import APIErrorCode
from app.abc.part import Part
from app.database import cruds, get_db
from app.dependencies import get_valid_session
from app.schemas import Member
from app.services import rbac
from app.utils import settings

router = APIRouter(tags=["Authentication"])

flow = Flow.from_client_secrets_file(
    "client_secret.json",
    scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    redirect_uri=settings["REDIRECT_URI"]
)


async def _build_member_detail(db: AsyncSession, member_id) -> dict:
    """groups / status_periods / roles をロードして dict を返す共通処理。"""
    loaded = await cruds.get_member_by_id(
        db,
        member_id,
        include_groups=True,
        include_status_periods=True,
    )
    if loaded is None:
        raise APIErrorCode.PERMISSION_DENIED.of("Member not found", 403)

    data = Member.model_validate(loaded).model_dump(mode="json")
    # selectinload 済みの属性を直接参照（model_validate 経由の lazy load を避ける）
    data["groups"] = [
        {"id": str(g.id), "display_name": g.display_name, "created_at": g.created_at.isoformat()}
        for g in (loaded.groups or [])
    ]
    data["membership_status_periods"] = [
        {
            "id": str(p.id),
            "member_id": str(p.member_id),
            "status_id": str(p.status_id),
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "created_at": p.created_at.isoformat(),
            "status": {
                "id": str(p.status.id),
                "display_name": p.status.display_name,
                "is_attendance_target": p.status.is_attendance_target,
                "default_attendance": p.status.default_attendance,
                "is_pre_attendance_excluded": p.status.is_pre_attendance_excluded,
            },
        }
        for p in (loaded.membership_status_periods or [])
    ]
    data["weekly_participations"] = []
    data["generation_role_keys"] = await rbac.generation_role_keys_for_generation(db, int(loaded.generation))
    data["member_role_keys"] = await rbac.member_role_keys_for_member(db, loaded.id)
    data["effective_role_keys"] = await rbac.effective_role_keys_for_member(db, loaded.id)
    data["effective_permission_keys"] = sorted(
        await rbac.effective_permission_keys_for_member(db, loaded.id)
    )
    return data


@router.post(
    "/login",
    summary="ログイン",
    description="Googleアカウントでログインします。",
)
async def login(request: Request, code: str = Form(), state: str = Form(),
                db: AsyncSession = Depends(get_db)):
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
    request.session.pop("state", None)

    return JSONResponse(await _build_member_detail(db, member.id))


@router.post(
    "/login/temp",
    summary="ログイン",
    description="ログインします。",
)
async def login_temp(request: Request, generation: int = Form(), part: Part = Form(), email: str = Form(),
                     db: AsyncSession = Depends(get_db)):
    member = await cruds.get_member_by_email(db, email)
    if not member or member.generation != generation or member.part != part:
        raise APIErrorCode.PERMISSION_DENIED.of("Permission denied", 403)

    token = await cruds.create_session(db, member)
    request.session["token"] = token
    request.session.pop("state", None)

    return JSONResponse(await _build_member_detail(db, member.id))


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
