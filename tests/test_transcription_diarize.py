"""FEAT-AUDIO-DIARIZE-001 — tests for diarized stage-1 transcription.

Offline unit tests run by default. The live Whisper/diarize API test is opt-in
via RUN_LIVE_DIARIZE=1 (costs real OpenAI usage).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.services.transcription import _normalize_diarized_segments, transcribe
from app.services.compiler import _build_labeled_transcript
from app.services.template_subtitles import _build_cues


# ---- Offline unit tests -----------------------------------------------------

def test_normalize_diarized_segments_shape():
    raw = [
        {"speaker": "A", "start": 0.0, "end": 2.5, "text": " Hello there "},
        {"speaker": "B", "start": 2.5, "end": 4.0, "text": "Hi"},
        {"speaker": "A", "start": 4.0, "end": 5.0, "text": ""},  # empty dropped
    ]
    out = _normalize_diarized_segments(raw)
    assert len(out) == 2
    assert out[0] == {"start": 0.0, "end": 2.5, "text": "Hello there", "speaker": "A"}
    assert all(isinstance(s["start"], float) and isinstance(s["end"], float) for s in out)
    assert all(s["speaker"] for s in out)


def test_build_labeled_transcript_groups_turns():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "Hello", "speaker": "A"},
        {"start": 1.0, "end": 2.0, "text": "there", "speaker": "A"},
        {"start": 2.0, "end": 3.0, "text": "Hi", "speaker": "B"},
    ]
    labeled = _build_labeled_transcript("Hello there Hi", segs)
    # consecutive same-speaker turns merge; speaker changes start a new line
    assert labeled == "Speaker A: Hello there\nSpeaker B: Hi"


def test_build_labeled_transcript_falls_back_when_no_speakers():
    plain = "just a plain transcript"
    assert _build_labeled_transcript(plain, []) == plain
    assert _build_labeled_transcript(plain, [{"start": 0, "end": 1, "text": "x"}]) == plain


def test_build_cues_prefixes_speaker_when_present():
    segs = [{"start": 0.0, "end": 2.0, "text": "Hello", "speaker": "A"}]
    cues = _build_cues(segs, "Hello")
    assert cues[0]["text"] == "A: Hello"


def test_build_cues_unchanged_without_speaker():
    segs = [{"start": 0.0, "end": 2.0, "text": "Hello"}]
    cues = _build_cues(segs, "Hello")
    assert cues[0]["text"] == "Hello"


# ---- Live integration test (opt-in) -----------------------------------------

@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_DIARIZE") != "1",
    reason="set RUN_LIVE_DIARIZE=1 to run the live diarize API test (costs usage)",
)
@pytest.mark.asyncio
async def test_live_diarize_returns_speakers():
    clip = os.environ.get("DIARIZE_CLIP", "/home/clawdbot/.claude/jobs/95e72ca1/tmp/clip90.mp3")
    assert Path(clip).exists(), f"test clip missing: {clip}"
    settings = Settings()
    settings.use_diarization = True
    result = await transcribe(clip, settings)
    assert result["success"], result.get("error")
    assert result.get("diarization_applied") is True
    segs = result["segments"]
    assert len(segs) > 0
    assert all(isinstance(s["start"], float) and isinstance(s["end"], float) for s in segs)
    speakers = {s.get("speaker") for s in segs}
    assert len(speakers) == 3, f"expected 3 speakers, got {sorted(speakers)}"
