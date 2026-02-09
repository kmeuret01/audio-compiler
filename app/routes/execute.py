"""Execute endpoint — runs compile_audio or transcribe_only."""

import logging
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import verify_token
from app.services.file_handler import validate_audio_file
from app.services.compiler import compile_audio
from app.services.transcription import transcribe
from app.tracing import run_stage

log = logging.getLogger("audio-compiler.execute")

router = APIRouter()


class ExecuteParams(BaseModel):
    audio_path: str
    language: Optional[str] = None
    overrides: Optional[dict] = None


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

    # Validate task
    if body.task not in ("compile_audio", "transcribe_only"):
        return {
            "success": False,
            "error": {"code": "INVALID_PARAMS", "message": f"Unknown task: {body.task}. Supported: compile_audio, transcribe_only"},
        }

    # Validate audio file
    error = validate_audio_file(body.params.audio_path, settings)
    if error:
        return {
            "success": False,
            "error": {"code": "INVALID_PARAMS", "message": error},
        }

    audio_format = Path(body.params.audio_path).suffix.lower()

    if body.task == "compile_audio":
        job_id = db.create_job(
            task="compile_audio",
            request_id=body.request_id,
            company_id=body.company_id,
            audio_path=body.params.audio_path,
            audio_format=audio_format,
        )
        try:
            result = await compile_audio(
                job_id=job_id,
                audio_path=body.params.audio_path,
                db=db,
                settings=settings,
                overrides=body.params.overrides,
            )
            return {
                "success": True,
                "job_id": job_id,
                "request_id": body.request_id,
                "result": result,
            }
        except Exception as e:
            log.error("compile_audio failed for job %s: %s", job_id, e, exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "request_id": body.request_id,
                "error": {"code": "INTERNAL_ERROR", "message": str(e)},
            }

    elif body.task == "transcribe_only":
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
