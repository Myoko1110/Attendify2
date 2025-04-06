from fastapi import FastAPI, HTTPException
from starlette.responses import JSONResponse

from .abc.api_error import APIError
from .database import db
from .routers import attendance, auth, member, schedule

app = FastAPI()
app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(member.router)
app.include_router(schedule.router)


@app.on_event("startup")
async def on_startup():
    await db.connect()


@app.get("/")
async def root():
    return {"message": "Hello World"}


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
