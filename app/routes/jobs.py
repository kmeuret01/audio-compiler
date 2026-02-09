"""Job status and trace endpoints."""

from fastapi import APIRouter, Depends, Request

from app.auth import verify_token

router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request, _token: str = Depends(verify_token)):
    db = request.app.state.db
    job = db.get_job(job_id)
    if not job:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Job {job_id} not found"}}
    return {"success": True, "job": job}


@router.get("/jobs/{job_id}/trace")
async def get_trace(job_id: str, request: Request, _token: str = Depends(verify_token)):
    db = request.app.state.db
    trace = db.get_trace(job_id)
    if not trace:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Job {job_id} not found"}}
    return {"success": True, "trace": trace}
