#!/usr/bin/env python3
"""DoD functional test: full pipeline on the real 60-min meeting, from the branch working tree."""
import asyncio, json, os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, "/home/clawdbot/audio-compiler")

from app.config import Settings
from app.database import Database
from app.services.compiler import compile_audio

REAL = "/home/clawdbot/kevin/audio/19fc8c36dddf3215/2026-08-03_11_21_59.mp3"

async def main():
    tmp = Path(tempfile.mkdtemp(prefix="diarize_ft_"))
    settings = Settings()
    settings.output_dir = str(tmp / "out")
    settings.db_path = str(tmp / "ft.db")
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    job_id = db.create_job(task="compile_audio", audio_path=REAL, audio_format=".mp3")
    print(f"job_id={job_id} out={settings.output_dir}")
    print(f"use_diarization={settings.use_diarization} model={settings.transcribe_model}")

    t = time.time()
    await compile_audio(job_id, REAL, db, settings, overrides={"tier": "enterprise"})
    print(f"pipeline wall={time.time()-t:.0f}s")

    out = Path(settings.output_dir) / job_id
    info = json.loads((out / "transcription_info.json").read_text())
    meta = json.loads((out / "metadata.json").read_text())
    transcript = (out / "transcript.txt").read_text()
    srt = (out / "subtitles.srt").read_text() if (out / "subtitles.srt").exists() else ""

    print("\n=== transcription_info.json ==="); print(json.dumps(info, indent=2))
    print("\n=== metadata (attendees/title) ===")
    print("title:", meta.get("title"))
    att = meta.get("attendees")
    print("attendees:", att)
    n_att = len(att) if isinstance(att, list) else att
    print("\n=== transcript head (speaker turns?) ===")
    print("\n".join(transcript.splitlines()[:6]))
    print("\n=== subtitles: first 2 cues ===")
    print("\n".join(srt.splitlines()[:8]))

    # ---- Assertions (DoD) ----
    fails = []
    if not info.get("diarization_applied"): fails.append("diarization_applied False")
    if info.get("speaker_count") != 3: fails.append(f"speaker_count={info.get('speaker_count')} (want 3)")
    if isinstance(n_att, int) and not (2 <= n_att <= 4): fails.append(f"attendee count {n_att} not in [2,4]")
    if "Speaker " not in transcript: fails.append("no speaker turns in transcript.txt")
    if not srt.strip(): fails.append("empty subtitles.srt")
    # SRT timestamps monotonic
    import re
    starts = [m.group(1) for m in re.finditer(r"(\d\d:\d\d:\d\d,\d\d\d) -->", srt)]
    if starts != sorted(starts): fails.append("SRT start times not monotonic")

    print("\n=== RESULT ===")
    if fails:
        print("FUNCTIONAL TEST FAILED:"); [print("  -", f) for f in fails]; sys.exit(1)
    print("FUNCTIONAL TEST PASSED — attendees:", n_att, "speakers:", info.get("speaker_count"))
    print("output dir:", out)

asyncio.run(main())
