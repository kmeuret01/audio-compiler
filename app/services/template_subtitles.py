"""
Subtitle template — generates SRT and VTT files from Whisper segments.

No LLM calls, no external libraries. Pure formatting of existing timestamp data.
"""

import logging
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("audio-compiler.output")


def _format_srt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS,mmm for SRT format."""
    total_ms = int(seconds * 1000)
    h = total_ms // 3_600_000
    m = (total_ms % 3_600_000) // 60_000
    s = (total_ms % 60_000) // 1_000
    ms = total_ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for VTT format."""
    total_ms = int(seconds * 1000)
    h = total_ms // 3_600_000
    m = (total_ms % 3_600_000) // 60_000
    s = (total_ms % 60_000) // 1_000
    ms = total_ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _build_cues(segments: List[dict], transcript: str) -> List[dict]:
    """
    Build subtitle cues from Whisper segments.

    Each cue: {index, start, end, text}

    If no segments, creates a single cue from the full transcript.
    """
    if not segments:
        return [{
            "index": 1,
            "start": 0.0,
            "end": 60.0,
            "text": transcript[:500] if transcript else "No transcript available.",
        }]

    cues = []
    for i, seg in enumerate(segments):
        start = seg.get("start", 0.0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        # FEAT-AUDIO-DIARIZE-001: prefix speaker label when present (backward
        # compatible — segments without a speaker render exactly as before).
        speaker = seg.get("speaker")
        if speaker:
            text = f"{speaker}: {text}"

        # End time: use next segment's start, or estimate from text length
        if i + 1 < len(segments):
            end = segments[i + 1].get("start", start + 5.0)
        else:
            # Last segment: estimate ~150 words/min reading speed
            word_count = len(text.split())
            end = start + max(2.0, word_count / 2.5)

        cues.append({
            "index": len(cues) + 1,
            "start": start,
            "end": end,
            "text": text,
        })

    return cues


def generate_srt(
    output_path: str,
    segments: Optional[List[dict]] = None,
    transcript: str = "",
) -> None:
    """
    Generate an SRT subtitle file.

    SRT format:
        1
        00:00:00,000 --> 00:00:05,000
        Speaker text here

        2
        00:00:05,000 --> 00:00:10,000
        More text here
    """
    cues = _build_cues(segments or [], transcript)

    lines = []
    for cue in cues:
        lines.append(str(cue["index"]))
        lines.append(f"{_format_srt_time(cue['start'])} --> {_format_srt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")  # blank line between cues

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    log.info("Generated SRT subtitle: %s (%d cues)", output_path, len(cues))


def generate_vtt(
    output_path: str,
    segments: Optional[List[dict]] = None,
    transcript: str = "",
) -> None:
    """
    Generate a WebVTT subtitle file.

    VTT format:
        WEBVTT

        00:00:00.000 --> 00:00:05.000
        Speaker text here

        00:00:05.000 --> 00:00:10.000
        More text here
    """
    cues = _build_cues(segments or [], transcript)

    lines = ["WEBVTT", ""]
    for cue in cues:
        lines.append(f"{_format_vtt_time(cue['start'])} --> {_format_vtt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")  # blank line between cues

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    log.info("Generated VTT subtitle: %s (%d cues)", output_path, len(cues))
