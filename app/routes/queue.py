"""Queue management endpoints."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/queue")
async def get_queue(request: Request):
    """Get current queue status."""
    qm = request.app.state.queue_manager
    return qm.get_queue_status()


@router.get("/queue/{job_id}")
async def get_job_queue_status(job_id: str, request: Request):
    """Get detailed status of a specific job in the queue."""
    qm = request.app.state.queue_manager
    status = qm.get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return status


@router.post("/queue/{job_id}/priority")
async def set_job_priority(job_id: str, request: Request, priority: int = 1):
    """Bump a queued job to high priority."""
    qm = request.app.state.queue_manager
    success = qm.set_priority(job_id, priority)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found or not in queued state"
        )
    return {"message": f"Job {job_id} priority set to {priority}"}


@router.post("/queue/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    """Cancel a queued job. Cannot cancel jobs already processing."""
    qm = request.app.state.queue_manager
    success = qm.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found or already processing"
        )
    return {"message": f"Job {job_id} cancelled"}
