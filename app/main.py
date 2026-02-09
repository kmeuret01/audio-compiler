"""Audio Compiler Module — FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.database import Database
from app.routes import health, capabilities, execute, jobs, feedback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("audio-compiler")


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

    log.info("Database: %s", settings.db_path)
    log.info("Output dir: %s", settings.output_dir)
    log.info("LLM model: %s", settings.llm_model)
    log.info("Ready")

    yield

    log.info("Shutting down")


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
