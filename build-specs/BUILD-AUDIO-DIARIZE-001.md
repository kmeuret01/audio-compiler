# BUILD SCRIPT — FEAT-AUDIO-DIARIZE-001 (driftproof, executable by a junior model)

> **You are finishing an approved, partially-built feature.** Do NOT redesign it.
> Do NOT expand scope. Execute the numbered steps exactly. If a step's acceptance
> check fails, STOP and report — do not improvise around it.

---

## 0. Authority & current state (read, do not skip)

- **Gate -1 plan review: APPROVED** 2026-08-03, plan_hash `b7bc06b23790afe9` (row in `plan_reviews` Postgres table, work_id `FEAT-AUDIO-DIARIZE-001`). Do not re-run Gate -1 unless you change scope.
- **Pre-sprint adversarial review:** `investigate` / medium / **non-blocking** (advisory). Findings already folded into this spec.
- **Repo:** `/home/clawdbot/audio-compiler` (standalone module; NOT rob-platform).
- **Branch:** `feat/audio-diarize-001`, tip commit `544028c`. All step-1 code below is ALREADY committed there. `git -C /home/clawdbot/audio-compiler checkout feat/audio-diarize-001` before doing anything.
- **Python:** use `/home/clawdbot/audio-compiler/venv/bin/python3` only. Never `python`.
- **Service:** systemd unit `audio-compiler.service` (uvicorn `app.main:app` on :8150).

### Already done on the branch (verified — do not redo)
- `app/config.py`: `use_diarization`, `transcribe_model=gpt-4o-transcribe-diarize`, `transcribe_response_format=diarized_json`, `transcribe_chunking_strategy=auto`, `transcribe_prompt`.
- `app/services/transcription.py`: `transcribe()` orchestrates → `_transcribe_diarize()` (speaker-labelled, timestamped segments) with **fail-open** to `_transcribe_whisper()` on ANY diarize error (logged WARNING, never silent). `_normalize_diarized_segments()` maps to `{start,end,text,speaker}`.
- `app/services/compiler.py`: `_build_labeled_transcript()` renders `Speaker A: ...` turns and feeds stages 2-5; writes `transcription_info.json` (observability marker: diarization_applied, speaker_count).
- `app/services/template_subtitles.py`: `_build_cues()` prefixes speaker (backward compatible).
- `tests/test_transcription_diarize.py`: 5 offline unit tests (PASS) + 1 opt-in live test (PASS on 90s & 300s clips → 3 speakers).

### The ONE open blocker you must fix (this is the whole job)
`gpt-4o-transcribe-diarize` **rejects the full 60-minute source file with HTTP 400 "Audio file might be corrupted or unsupported"**, even though a 5-minute slice of the *same* file diarizes fine (3 speakers). So the failure is duration/size-bound, not encoding. On the full file the code correctly falls back to whisper-1 → NO speaker labels → the original bug (12–13 attendees for a 3-person meeting) persists on real meetings.

**Reproduction (run this first to see the 400):**
```bash
cd /home/clawdbot/audio-compiler && set -a && source .env && set +a
venv/bin/python3 - <<'PY'
import asyncio; from app.config import Settings
from app.services.transcription import _transcribe_diarize
from pathlib import Path
s=Settings(); s.use_diarization=True
r=asyncio.run(_transcribe_diarize(Path("/home/clawdbot/kevin/audio/19fc8c36dddf3215/2026-08-03_11_21_59.mp3"), s, 0.0, None))
print(r["success"], r.get("error"))   # expect: False  ...400 corrupted/unsupported
PY
```

---

## 1. STEP A — Diagnostic spike (decide the fix; ~10 min, small cost)

Run exactly these two probes on the real file and record which succeeds. Use the
helper pattern from `tests/test_transcription_diarize.py` (multipart POST to
`https://api.openai.com/v1/audio/transcriptions`, model `gpt-4o-transcribe-diarize`,
`response_format=diarized_json`, `chunking_strategy=auto`). Source file:
`/home/clawdbot/kevin/audio/19fc8c36dddf3215/2026-08-03_11_21_59.mp3`.

- **Probe 1 (re-mux, cheap):** `ffmpeg -y -i SRC -c copy /tmp/remux_full.mp3` then diarize `/tmp/remux_full.mp3`.
- **Probe 2 (chunk):** split into 10-minute WAV chunks:
  `ffmpeg -y -i SRC -f segment -segment_time 600 -ar 16000 -ac 1 /tmp/chunk_%03d.wav`
  then diarize each chunk individually.

**Decision rule (no judgment — follow the table):**

| Outcome | Implement in STEP B |
|---|---|
| Probe 1 succeeds (full re-muxed file diarizes) | **Re-mux path**: transcode to a clean file before the diarize POST. Simplest. |
| Probe 1 fails, Probe 2 succeeds (each chunk diarizes) | **Chunking path**: diarize per chunk, then stitch (see B2). |
| Both fail | **STOP.** Report to Kevin. Keep whisper-1 fallback as the shipped behavior. Do not force it. |

---

## 2. STEP B — Implement the winning path (isolated to transcription.py)

### B1 — Re-mux path (if Probe 1 won)
In `_transcribe_diarize()`, before building the multipart body, transcode the input to a temp file via `subprocess.run(["ffmpeg","-y","-i",str(path),"-ar","16000","-ac","2","/tmp/<uuid>.wav"], ...)` and POST that temp file (clean up after). Keep everything else identical. Keep the fail-open to whisper-1.

### B2 — Chunking path (if Probe 2 won)
Add `_transcribe_diarize_chunked()`:
1. `ffmpeg` split source into ≤10-min WAV chunks (record each chunk's start offset in seconds).
2. Diarize each chunk sequentially.
3. **Stitch:** add each chunk's start offset to every segment `start`/`end`. Concatenate segments in order.
4. **Speaker-label consistency across chunks is NOT guaranteed** by the API (chunk 2's "A" ≠ chunk 1's "A"). For v1, prefix labels with the chunk index (`A` → `1-A`) so labels stay honest rather than falsely merged. Cross-chunk speaker re-identification is explicitly OUT OF SCOPE — log it as a follow-up, do not attempt.
5. Route `_transcribe_diarize()` to the chunked variant when the file duration exceeds a threshold (e.g. > 8 min via `_get_duration`), else single-shot.

Keep the fail-open: if chunking raises, log WARNING and return `{"success": False, ...}` so `transcribe()` falls back to whisper-1.

---

## 3. STEP C — Acceptance gate (all must PASS; real data, not clips)

```bash
cd /home/clawdbot/audio-compiler && set -a && source .env && set +a
# 3.1 offline unit suite
venv/bin/python3 -m pytest tests/test_transcription_diarize.py -q          # 5 passed, 1 skipped
# 3.2 live clip test
RUN_LIVE_DIARIZE=1 venv/bin/python3 -m pytest tests/test_transcription_diarize.py::test_live_diarize_returns_speakers -q
# 3.3 FULL real-file functional test (the gate that currently fails)
venv/bin/python3 build-specs/functional_test_diarize.py
```
`functional_test.py` asserts, on the real 60-min file: `diarization_applied == true`,
`speaker_count == 3`, metadata attendee count in `[2,4]` (NOT 13), non-empty
`subtitles.srt` with monotonic timestamps, and `Speaker ` turns in `transcript.txt`.
**If a chunking path made labels `1-A` etc., update the test's `speaker_count == 3`
assertion to "≥3 distinct base speakers" — but ONLY that assertion.**

**DO NOT declare done until 3.3 passes on the full file.** A passing clip is not sufficient (that is the exact trap that produced this blocker).

---

## 4. Scope boundaries (hard limits)
- ONLY edit `app/config.py`, `app/services/transcription.py`, and — only if a chunk-label change forces it — `tests/test_transcription_diarize.py`.
- **DO NOT** edit the 5 verbatim LLM prompts in `compiler.py` (module CLAUDE.md forbids it).
- **DO NOT** touch the email intake/send flow (`email_commander.py`, `attachment_handler.py`, `notifier.py`), the `/execute` route contract, or the DB schema.
- **DO NOT** touch anything under `/home/clawdbot/rob-platform`.
- **DO NOT** edit `.env` values in code; new settings ship as `config.py` defaults only.

## 5. Post-build gates (protocol — mandatory before merge)
1. Post-sprint adversarial implementation review: `POST http://localhost:8152/execute/adversarial_critique` (body `{"tool":"adversarial_critique","params":{claim,data,context}}`) with files changed + test results. Resolve/justify any blocking finding.
2. Smoke test: `sudo systemctl restart audio-compiler.service` then `curl -s http://127.0.0.1:8150/health` → 200, and one real compile_audio job reaches `status=completed`.
3. Commit on `feat/audio-diarize-001`, then request Kevin's merge approval. Do NOT merge to `main` yourself.

## 6. Rollback (if anything regresses in prod)
- Instant: set `USE_DIARIZATION=false` in `/home/clawdbot/audio-compiler/.env`, then `sudo systemctl restart audio-compiler.service` → reverts to whisper-1, zero code change.
- Full: `git -C /home/clawdbot/audio-compiler revert --no-edit <merge_sha> && sudo systemctl restart audio-compiler.service`.
