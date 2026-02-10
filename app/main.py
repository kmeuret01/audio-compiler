"""Audio Compiler Module — FastAPI application."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.database import Database
from app.queue_manager import QueueManager
from app.routes import health, capabilities, execute, jobs, feedback, queue
from app.services.compiler import compile_audio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("audio-compiler")


async def process_job_wrapper(job_id: str, audio_path: str) -> bool:
    """Wrapper that calls compile_audio and returns success/failure."""
    try:
        db = app.state.db
        settings = app.state.settings

        result = await compile_audio(
            job_id=job_id,
            audio_path=audio_path,
            db=db,
            settings=settings,
        )
        return result.get("status") == "completed"
    except Exception as e:
        log.error(f"compile_audio failed for job {job_id}: {e}", exc_info=True)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Audio Compiler v%s starting up", settings.module_version)

    # Ensure directories exist
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    # Initialize database
    db = Database(settings.db_path)
    app.state.db = db
    app.state.settings = settings

    # Initialize queue manager
    queue_manager = QueueManager(
        db_path=settings.db_path,
        process_job_func=process_job_wrapper,
    )
    app.state.queue_manager = queue_manager
    await queue_manager.startup()

    log.info("Database: %s", settings.db_path)
    log.info("Output dir: %s", settings.output_dir)
    log.info("LLM model: %s", settings.llm_model)
    log.info("Queue manager: enabled")
    log.info("Ready")

    yield

    log.info("Shutting down")
    await queue_manager.shutdown()


app = FastAPI(
    title="Audio Compiler Module",
    version="1.0.0",
    description="ROI Logistics Audio Compilation Pipeline — transcribe, analyze, and generate branded PDFs from audio recordings.",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(capabilities.router)
app.include_router(execute.router)
app.include_router(jobs.router)
app.include_router(feedback.router)
app.include_router(queue.router)
