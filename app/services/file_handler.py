"""File handling — validation, temp storage, cleanup."""

from pathlib import Path

from app.config import Settings

SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".mpeg", ".mpga"}


def validate_audio_file(file_path: str, settings: Settings) -> str | None:
    """Validate an audio file. Returns error string or None if valid."""
    path = Path(file_path)
    if not path.exists():
        return f"File not found: {file_path}"
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        return f"Unsupported format: {path.suffix}. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if path.stat().st_size > max_bytes:
        return f"File too large ({path.stat().st_size} bytes). Max is {settings.max_file_size_mb}MB."
    return None


def ensure_output_dir(job_id: str, settings: Settings) -> Path:
    """Create and return the per-job output directory."""
    output_dir = Path(settings.output_dir) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def cleanup_job_files(job_id: str, settings: Settings) -> None:
    """Remove temp files for a job (uploads only, not outputs)."""
    upload_dir = Path(settings.upload_dir) / job_id
    if upload_dir.exists():
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)
