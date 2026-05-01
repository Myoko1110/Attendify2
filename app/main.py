import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import FileResponse, JSONResponse

from .abc.api_error import APIError
from .dependencies import get_valid_session, require_permission
from .routers import attendance, attendance_export, attendance_log, auth, constant, group, member, membership_status, pre_attendance, \
    rbac, schedule
from .services.attendance_service import auto_insert_daily_attendances
from .utils import save_setting_data, settings

app = FastAPI()

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(attendance.router)
api.include_router(attendance_export.router)
api.include_router(rbac.router)
api.include_router(member.router)
api.include_router(membership_status.router)
api.include_router(group.router)
api.include_router(schedule.router)
api.include_router(pre_attendance.router)
api.include_router(constant.router)
api.include_router(attendance_log.router)

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


async def _ensure_scheduler_started() -> dict:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is None:
        scheduler = AsyncIOScheduler()
        auto_insert_time = settings.get("AUTO_INSERT_TIME", "21:00")
        hour, minute = map(int, auto_insert_time.split(":"))
        scheduler.add_job(
            auto_insert_daily_attendances,
            "cron",
            hour=hour,
            minute=minute,
            replace_existing=True,
            id="auto_insert_daily_attendances",
        )
        app.state.scheduler = scheduler

    if not scheduler.running:
        scheduler.start()
    app.state.scheduler_enabled = True
    settings["SCHEDULER_ENABLED"] = True
    save_setting_data(settings)
    return {"enabled": True, "running": scheduler.running}


async def _ensure_scheduler_stopped() -> dict:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
    app.state.scheduler_enabled = False
    settings["SCHEDULER_ENABLED"] = False
    save_setting_data(settings)
    return {"enabled": False, "running": False}


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


@app.get(
    "/api/scheduler/status",
    summary="スケジューラの状態を確認",
    dependencies=[Depends(require_permission("attendance-log:read"))],
)
async def get_scheduler_status():
    scheduler = getattr(app.state, "scheduler", None)
    running = scheduler.running if scheduler else False
    enabled = getattr(app.state, "scheduler_enabled", running)
    jobs = scheduler.get_jobs() if scheduler else []
    return dict(
        enabled=enabled,
        running=running,
        next_run_time=jobs[0].next_run_time.isoformat() if jobs else None,
    )


@app.post(
    "/api/scheduler/start",
    summary="スケジューラを開始",
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def start_scheduler():
    return await _ensure_scheduler_started()


@app.post(
    "/api/scheduler/stop",
    summary="スケジューラを停止",
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def stop_scheduler():
    return await _ensure_scheduler_stopped()


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
def on_internal_exception_handler(request, exc: Exception):
    # If this 404 originated from our APIError (subclass of HTTPException), preserve the error detail and code.
    from .abc.api_error import APIError
    if isinstance(exc, APIError):
        return JSONResponse(status_code=exc.status_code, content=dict(
            error=exc.detail,
            error_code=exc.code,
        ))

    # For other 404s (e.g., missing routes), return a generic message.
    return JSONResponse(status_code=404, content=dict(
        error="Page Not Found",
        error_code=-1,
    ))


@app.on_event("startup")
async def on_startup():
    from .database import migrate
    await migrate()
    print("Database migrated.")

    if settings.get("SCHEDULER_ENABLED", True):
        await _ensure_scheduler_started()
        print("Scheduler started.")
    else:
        app.state.scheduler_enabled = False
        print("Scheduler is disabled.")


@app.on_event("shutdown")
async def on_shutdown():
    # APScheduler のスケジューラを停止
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.shutdown()
            print("Scheduler stopped.")
        except Exception:
            print("Failed to shutdown scheduler.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
