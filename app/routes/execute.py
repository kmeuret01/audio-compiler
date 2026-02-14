"""Execute endpoint — enqueues compile_audio, transcribe_only, or compile_transcript."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import verify_token
from app.services.file_handler import validate_audio_file
from app.services.transcription import transcribe
from app.tracing import run_stage

log = logging.getLogger("audio-compiler.execute")

router = APIRouter()


class ExecuteParams(BaseModel):
    audio_path: Optional[str] = ""
    transcript: Optional[str] = None  # Pre-transcribed text (for compile_transcript)
    language: Optional[str] = None
    overrides: Optional[dict] = None
    submitter_email: Optional[str] = ""
    submitter_name: Optional[str] = ""
    priority: Optional[int] = 0
    thread_id: Optional[str] = ""  # Gmail thread ID for reply-in-thread
    tier: Optional[str] = "advanced"  # basic, advanced, enterprise


class ExecuteRequest(BaseModel):
    request_id: str = ""
    company_id: str = "roi-logistics"
    task: str
    params: ExecuteParams
    context: Optional[dict] = None
    timestamp: Optional[str] = None


@router.post("/execute")
async def execute(body: ExecuteRequest, request: Request, _token: str = Depends(verify_token)):
    db = request.app.state.db
    settings = request.app.state.settings
    queue_manager = request.app.state.queue_manager

    # Validate task
    if body.task not in ("compile_audio", "transcribe_only", "compile_transcript"):
        return {
            "success": False,
            "error": {"code": "INVALID_PARAMS", "message": f"Unknown task: {body.task}. Supported: compile_audio, transcribe_only, compile_transcript"},
        }

    # compile_transcript skips audio file validation
    if body.task == "compile_transcript":
        transcript_text = body.params.transcript or ""
        if len(transcript_text.strip()) < 50:
            return {
                "success": False,
                "error": {"code": "INVALID_PARAMS", "message": "Transcript must be at least 50 characters"},
            }

        job_id = db.create_job(
            task="compile_transcript",
            request_id=body.request_id,
            company_id=body.company_id,
            audio_path="transcript://voice-session",
            audio_format="text",
            thread_id=body.params.thread_id or "",
        )

        try:
            file_size = len(transcript_text.encode("utf-8"))
            tier = body.params.tier or "advanced"
            overrides_json = json.dumps({"transcript": transcript_text, "tier": tier})

            queue_result = await queue_manager.enqueue_job(
                job_id=job_id,
                audio_path="transcript://voice-session",
                submitter_email=body.params.submitter_email or "",
                submitter_name=body.params.submitter_name or "",
                file_size_bytes=file_size,
                priority=body.params.priority or 0,
                thread_id=body.params.thread_id or "",
                overrides_json=overrides_json,
            )

            return {
                "success": True,
                "job_id": job_id,
                "request_id": body.request_id,
                "queued": True,
                "queue_position": queue_result["queue_position"],
                "estimated_wait_seconds": queue_result["estimated_wait_seconds"],
                "message": queue_result["message"],
            }
        except Exception as e:
            log.error("Failed to enqueue compile_transcript job %s: %s", job_id, e, exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "request_id": body.request_id,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    # Validate audio file (for compile_audio and transcribe_only)
    error = validate_audio_file(body.params.audio_path, settings)
    if error:
        return {
            "success": False,
            "error": {"code": "INVALID_PARAMS", "message": error},
        }

    audio_format = Path(body.params.audio_path).suffix.lower()

    if body.task == "compile_audio":
        # Create job record
        job_id = db.create_job(
            task="compile_audio",
            request_id=body.request_id,
            company_id=body.company_id,
            audio_path=body.params.audio_path,
            audio_format=audio_format,
            thread_id=body.params.thread_id or "",
        )

        # Get file size for duration estimation
        try:
            file_size = os.path.getsize(body.params.audio_path)
        except OSError:
            file_size = 0

        # Enqueue instead of processing inline
        tier = body.params.tier or "advanced"
        tier_overrides = json.dumps({"tier": tier}) if tier != "advanced" else ""
        try:
            queue_result = await queue_manager.enqueue_job(
                job_id=job_id,
                audio_path=body.params.audio_path,
                submitter_email=body.params.submitter_email or "",
                submitter_name=body.params.submitter_name or "",
                file_size_bytes=file_size,
                priority=body.params.priority or 0,
                thread_id=body.params.thread_id or "",
                overrides_json=tier_overrides,
            )

            return {
                "success": True,
                "job_id": job_id,
                "request_id": body.request_id,
                "queued": True,
                "queue_position": queue_result["queue_position"],
                "estimated_wait_seconds": queue_result["estimated_wait_seconds"],
                "message": queue_result["message"],
            }
        except Exception as e:
            log.error("Failed to enqueue job %s: %s", job_id, e, exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "request_id": body.request_id,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    elif body.task == "transcribe_only":
        # transcribe_only still runs inline (it's fast)
        job_id = db.create_job(
            task="transcribe_only",
            request_id=body.request_id,
            company_id=body.company_id,
            audio_path=body.params.audio_path,
            audio_format=audio_format,
        )
        try:
            db.update_job_status(job_id, "processing")
            result = await run_stage(
                job_id, "stage_1_transcription", db,
                transcribe, body.params.audio_path, settings, body.params.language,
                input_summary=f"Audio file: {Path(body.params.audio_path).name}",
                llm_model="whisper-1",
            )
            if result["success"]:
                # Save transcript
                output_dir = Path(settings.output_dir) / job_id
                output_dir.mkdir(parents=True, exist_ok=True)
                transcript_path = output_dir / "transcript.txt"
                transcript_path.write_text(result["transcript"], encoding="utf-8")

                db.complete_job(job_id, total_duration_ms=0, output_dir=str(output_dir),
                                audio_duration=result.get("duration_seconds", 0))
                return {
                    "success": True,
                    "job_id": job_id,
                    "request_id": body.request_id,
                    "result": {
                        "transcript": result["transcript"],
                        "word_count": result["word_count"],
                        "duration_seconds": result["duration_seconds"],
                        "output_dir": str(output_dir),
                    },
                }
            else:
                db.fail_job(job_id, result["error"])
                return {
                    "success": False,
                    "job_id": job_id,
                    "request_id": body.request_id,
                    "error": {"code": "EXTERNAL_API_ERROR", "message": result["error"]},
                }
        except Exception as e:
            log.error("transcribe_only failed for job %s: %s", job_id, e, exc_info=True)
            db.fail_job(job_id, str(e))
            return {
                "success": False,
                "job_id": job_id,
                "request_id": body.request_id,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }
