import datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, JSONResponse

from .abc.api_error import APIError
from .dependencies import get_valid_session
from .routers import attendance, auth, constant, group, member, membership_status, pre_attendance, \
    schedule
from .utils import settings

app = FastAPI()

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(attendance.router)
api.include_router(member.router)
api.include_router(membership_status.router)
api.include_router(group.router)
api.include_router(schedule.router)
api.include_router(pre_attendance.router)
api.include_router(constant.router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get("ORIGINS"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key="64b75f34602a43f95f9ebf93857309ab55aecb67bdb2245782746c7316e3477a",
    https_only=True,
    same_site="strict"
)


@app.get(
    "/db",
    summary="データベースをダウンロード",
    dependencies=[Depends(get_valid_session)],
)
async def get_db():
    now = datetime.datetime.now()
    return FileResponse(
        path="attendify.db",
        filename=f"attendify_{now.strftime('%Y%m%d%H%M%S')}.db",
    )


@app.exception_handler(HTTPException)
def on_api_error(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=dict(
        error=exc.detail,
        error_code=exc.code if isinstance(exc, APIError) else -1,
    ))


@app.exception_handler(500)
def on_internal_exception_handler(_, __: Exception):
    return JSONResponse(status_code=500, content=dict(
        error="Internal Server Error",
        error_code=-1,
    ))


@app.exception_handler(404)
def on_internal_exception_handler(_, __: Exception):
    return JSONResponse(status_code=404, content=dict(
        error="Page Not Found",
        error_code=-1,
    ))


@app.on_event("startup")
async def on_startup():
    from .database import migrate
    await migrate()
    print("Database migrated.")

