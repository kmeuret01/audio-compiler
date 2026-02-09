"""Health check — no auth required."""

import time

from fastapi import APIRouter, Request

router = APIRouter()
_start_time = time.monotonic()


@router.get("/health")
async def health(request: Request):
    db = request.app.state.db
    settings = request.app.state.settings

    # DB check
    db_ok = False
    try:
        job = db.get_job("__probe__")  # Will return None, but proves DB is queryable
        db_ok = True
    except Exception:
        pass

    counts = {}
    try:
        counts = db.get_job_counts(24)
    except Exception:
        pass

    uptime_s = int(time.monotonic() - _start_time)

    return {
        "module": settings.module_name,
        "version": settings.module_version,
        "status": "healthy" if db_ok and settings.openai_api_key else "degraded",
        "uptime_seconds": uptime_s,
        "checks": {
            "openai_api_key": bool(settings.openai_api_key),
            "database": db_ok,
        },
        "jobs": counts,
    }
