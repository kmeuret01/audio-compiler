"""Transcription service — consolidated Whisper API client."""

import subprocess
from pathlib import Path
from typing import Optional

import httpx

from app.config import Settings

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".mpeg", ".mpga"}


async def transcribe(file_path: str, settings: Settings, language: Optional[str] = None) -> dict:
    """Transcribe audio via OpenAI Whisper API.

    Returns:
        {"success": bool, "transcript": str, "duration_seconds": float,
         "word_count": int, "error": str|None, "usage": dict}
    """
    path = Path(file_path)
    if not path.exists():
        return {"success": False, "transcript": "", "duration_seconds": 0,
                "word_count": 0, "error": f"File not found: {file_path}"}

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        return {"success": False, "transcript": "", "duration_seconds": 0,
                "word_count": 0, "error": f"Unsupported format: {path.suffix}"}

    file_size = path.stat().st_size
    max_size = 25 * 1024 * 1024
    if file_size > max_size:
        return {"success": False, "transcript": "", "duration_seconds": 0,
                "word_count": 0, "error": f"File too large ({file_size} bytes). Max is 25MB."}

    # Get duration via ffprobe if available
    duration = _get_duration(file_path)

    try:
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {"model": settings.whisper_model, "response_format": "text"}
            if language:
                data["language"] = language

            async with httpx.AsyncClient(timeout=settings.whisper_timeout) as client:
                resp = await client.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files=files,
                    data=data,
                )

        if resp.status_code != 200:
            return {"success": False, "transcript": "", "duration_seconds": duration,
                    "word_count": 0, "error": f"Whisper API error: {resp.status_code} - {resp.text}"}

        transcript = resp.text.strip()
        return {
            "success": True,
            "transcript": transcript,
            "duration_seconds": duration,
            "word_count": len(transcript.split()),
            "error": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    except httpx.TimeoutException:
        return {"success": False, "transcript": "", "duration_seconds": duration,
                "word_count": 0, "error": f"Whisper API timed out after {settings.whisper_timeout}s"}
    except Exception as e:
        return {"success": False, "transcript": "", "duration_seconds": duration,
                "word_count": 0, "error": str(e)}


def _get_duration(audio_path: str) -> float:
    """Get audio duration in seconds via ffprobe. Returns 0 on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


async def extract_audio_from_video(video_path: str, output_path: Optional[str] = None) -> dict:
    """Extract audio track from a video file."""
    path = Path(video_path)
    if not path.exists():
        return {"success": False, "error": f"File not found: {video_path}"}

    if output_path is None:
        output_path = str(path.with_suffix(".mp3"))

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame",
             "-q:a", "2", output_path],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            return {"success": True, "audio_path": output_path}
        return {"success": False, "error": result.stderr}
    except FileNotFoundError:
        return {"success": False, "error": "ffmpeg not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}
