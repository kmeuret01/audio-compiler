"""Job status and trace endpoints."""

import json

from fastapi import APIRouter, Depends, Request

from app.auth import verify_token

router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request, _token: str = Depends(verify_token)):
    db = request.app.state.db
    job = db.get_job(job_id)
    if not job:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Job {job_id} not found"}}
    job["deliverables"] = _parse_deliverables(job.get("deliverables"))
    return {"success": True, "job": job}


def _parse_deliverables(raw: str | None) -> dict | None:
    """The stored deliverables manifest as a dict; None when absent or malformed."""
    if not raw:
        return None
    try:
        manifest = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


@router.get("/jobs/{job_id}/trace")
async def get_trace(job_id: str, request: Request, _token: str = Depends(verify_token)):
    db = request.app.state.db
    trace = db.get_trace(job_id)
    if not trace:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Job {job_id} not found"}}
    return {"success": True, "trace": trace}
