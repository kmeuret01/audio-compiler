"""Feedback endpoint — stores quality feedback linked to jobs."""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import verify_token

router = APIRouter()


class FeedbackRequest(BaseModel):
    job_id: Optional[str] = ""
    company_id: str = "roi-logistics"
    feedback_type: str
    issue: str
    details: Optional[str] = ""
    source: str = "slack"


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest, request: Request, _token: str = Depends(verify_token)):
    db = request.app.state.db
    feedback_id = db.save_feedback(
        feedback_type=body.feedback_type,
        issue=body.issue,
        job_id=body.job_id,
        company_id=body.company_id,
        details=body.details,
        source=body.source,
    )
    return {"success": True, "feedback_id": feedback_id}
