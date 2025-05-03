from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

from .abc.api_error import APIError
from .database import db
from .routers import attendance, auth, constant, member, schedule

app = FastAPI()

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(attendance.router)
api.include_router(member.router)
api.include_router(schedule.router)
api.include_router(constant.router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3039"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key="64b75f34602a43f95f9ebf93857309ab55aecb67bdb2245782746c7316e3477a")


@app.on_event("startup")
async def on_startup():
    await db.connect()


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
