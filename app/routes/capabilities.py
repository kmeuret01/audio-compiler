"""Capabilities endpoint — returns what this module can do."""

from fastapi import APIRouter, Depends

from app.auth import verify_token

router = APIRouter()


@router.get("/capabilities")
async def capabilities(_token: str = Depends(verify_token)):
    return {
        "module": "audio-compiler",
        "version": "1.0.0",
        "capabilities": [
            {
                "task": "compile_audio",
                "description": "Full audio compilation: transcribe, then three GoAI Labs files — meeting notes PDF, transcript PDF, and an agent-ready markdown with the full transcript.",
                "params": {
                    "audio_path": {"type": "string", "required": True, "description": "Path to audio file on shared filesystem"},
                    "language": {"type": "string", "required": False, "description": "ISO language code hint for Whisper"},
                    "overrides": {"type": "object", "required": False, "description": "Pre-computed fields to skip LLM passes (transcript, metadata, notes, action_items, summary)"},
                },
                "outputs": [
                    "transcript.txt", "metadata.json", "meeting_notes.md",
                    "action_items.json", "summary.md", "quality_review.json",
                    "report.json",
                    "{Meeting Name - YYYY-MM-DD} Meeting Notes.pdf",
                    "{Meeting Name - YYYY-MM-DD} Transcript.pdf",
                    "{Meeting Name - YYYY-MM-DD} Agent Ready Markdown.md",
                ],
            },
            {
                "task": "transcribe_only",
                "description": "Whisper transcription only — no LLM analysis passes.",
                "params": {
                    "audio_path": {"type": "string", "required": True, "description": "Path to audio file on shared filesystem"},
                    "language": {"type": "string", "required": False, "description": "ISO language code hint for Whisper"},
                },
                "outputs": ["transcript.txt"],
            },
        ],
    }
