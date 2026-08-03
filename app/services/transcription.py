"""Transcription service — consolidated Whisper API client."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import httpx

from app.config import Settings

log = logging.getLogger("audio-compiler.transcription")

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

    # FEAT-AUDIO-DIARIZE-001: prefer diarized transcription (speaker labels), but
    # fail open to whisper-1 on any error so a transient diarize failure never
    # breaks a job. The fallback is logged (never silent).
    if getattr(settings, "use_diarization", False):
        diar = await _transcribe_diarize(path, settings, duration, language)
        if diar["success"]:
            return diar
        log.warning(
            "Diarization failed (%s); falling back to whisper model '%s'",
            diar.get("error"), settings.whisper_model,
        )

    return await _transcribe_whisper(path, settings, duration, language)


async def _transcribe_whisper(path: Path, settings: Settings, duration: float,
                              language: Optional[str]) -> dict:
    """Legacy whisper-1 path: verbose_json with segment timestamps, no speaker labels."""
    try:
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {"model": settings.whisper_model, "response_format": "verbose_json"}
            if language:
                data["language"] = language
            prompt = getattr(settings, "transcribe_prompt", "") or ""
            if prompt:
                data["prompt"] = prompt

            async with httpx.AsyncClient(timeout=settings.whisper_timeout) as client:
                resp = await client.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files=files,
                    data=data,
                )

        if resp.status_code != 200:
            return {"success": False, "transcript": "", "duration_seconds": duration,
                    "word_count": 0, "segments": [], "diarization_applied": False,
                    "error": f"Whisper API error: {resp.status_code} - {resp.text}"}

        result_json = resp.json()
        transcript = result_json.get("text", "").strip()
        segments = result_json.get("segments", [])
        if not duration and result_json.get("duration"):
            duration = result_json["duration"]

        return {
            "success": True,
            "transcript": transcript,
            "duration_seconds": duration,
            "word_count": len(transcript.split()),
            "segments": segments,
            "diarization_applied": False,
            "error": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    except httpx.TimeoutException:
        return {"success": False, "transcript": "", "duration_seconds": duration,
                "word_count": 0, "segments": [], "diarization_applied": False,
                "error": f"Whisper API timed out after {settings.whisper_timeout}s"}
    except Exception as e:
        return {"success": False, "transcript": "", "duration_seconds": duration,
                "word_count": 0, "segments": [], "diarization_applied": False,
                "error": str(e)}


async def _transcribe_diarize(path: Path, settings: Settings, duration: float,
                              language: Optional[str]) -> dict:
    """Diarized path: gpt-4o-transcribe-diarize with speaker-labelled, timestamped segments."""
    try:
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            data = {
                "model": settings.transcribe_model,
                "response_format": settings.transcribe_response_format,
                "chunking_strategy": settings.transcribe_chunking_strategy,
            }
            if language:
                data["language"] = language
            prompt = getattr(settings, "transcribe_prompt", "") or ""
            if prompt:
                data["prompt"] = prompt

            async with httpx.AsyncClient(timeout=settings.whisper_timeout) as client:
                resp = await client.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files=files,
                    data=data,
                )

        if resp.status_code != 200:
            return {"success": False, "segments": [], "diarization_applied": False,
                    "error": f"Diarize API error: {resp.status_code} - {resp.text[:300]}"}

        result_json = resp.json()
        segments = _normalize_diarized_segments(result_json.get("segments", []))
        if not segments:
            return {"success": False, "segments": [], "diarization_applied": False,
                    "error": "Diarize returned no usable segments"}

        transcript = result_json.get("text", "").strip()
        if not transcript:
            transcript = " ".join(s["text"] for s in segments)
        if not duration and result_json.get("duration"):
            duration = float(result_json["duration"])

        return {
            "success": True,
            "transcript": transcript,
            "duration_seconds": duration,
            "word_count": len(transcript.split()),
            "segments": segments,
            "diarization_applied": True,
            "error": None,
            "usage": result_json.get("usage", {}),
        }

    except httpx.TimeoutException:
        return {"success": False, "segments": [], "diarization_applied": False,
                "error": f"Diarize API timed out after {settings.whisper_timeout}s"}
    except Exception as e:
        return {"success": False, "segments": [], "diarization_applied": False,
                "error": str(e)}


def _normalize_diarized_segments(raw_segments: list) -> list:
    """Map diarized API segments to the pipeline's {start,end,text,speaker} shape.

    Drops empty-text segments; coerces timestamps to float. Preserves order.
    """
    out = []
    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "start": float(seg.get("start", 0.0) or 0.0),
            "end": float(seg.get("end", 0.0) or 0.0),
            "text": text,
            "speaker": seg.get("speaker") or "?",
        })
    return out


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
