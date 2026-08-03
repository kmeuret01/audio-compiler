# Handoff — Audio Transcriber Diarization Upgrade (FEAT-AUDIO-DIARIZE-001)

**Prepared for:** Kevin Meuret
**Date:** 2026-08-03
**Status:** Design approved + core code built & branch-committed. **One open blocker** remains before it works on full-length recordings. Ready to hand to a build model.

---

## 1. What you asked
Assess whether the MP3→transcript step of your audio compiler (built ~6 months ago) needs upgrading, using only APIs you already pay for — then take the upgrade forward.

## 2. What I found (evidence-based)
- Your transcriber is a standalone service at `/home/clawdbot/audio-compiler` (Whisper `whisper-1`) on port 8150.
- **Root quality problem:** `whisper-1` returns text with **no speaker labels**, so the downstream LLM stages guess who spoke. On your real 2026-08-03 meeting (job `e5c05281-58c`) it extracted **13 attendees for a 3-person call** (you, Dave, Jacob).
- **The upgrade:** your OpenAI key now exposes **`gpt-4o-transcribe-diarize`** — real speaker separation *with* timestamps. On 90-second and 5-minute clips of your actual meeting it correctly returned **exactly 3 speakers (A/B/C)**. This is a genuine quality jump, not marginal.
- **Rejected alternative:** plain `gpt-4o-transcribe` refuses `verbose_json` (HTTP 400) → it would silently break your SRT/VTT subtitles. Diarize is the only timestamp-preserving option.

## 3. What's been built (on branch `feat/audio-diarize-001`, commit `544028c`)
- Feature-flagged diarized transcription with **fail-open fallback to whisper-1** (a diarize failure never breaks a job — it's logged, never silent).
- Speaker-labelled transcript fed to the downstream stages (fixes the attribution bug at the source).
- Speaker-prefixed subtitles (backward compatible) + a `transcription_info.json` marker so a silent fallback is diagnosable.
- Tests: 5 offline unit tests pass; live diarize test passes on clips (3 speakers).
- **Both mandatory gates cleared:** Gate -1 dual-model plan review **APPROVED** (hash `b7bc06b23790afe9`); pre-sprint adversarial review returned *advisory / non-blocking*.

## 4. The open blocker (why it's not shippable yet)
The diarize model **rejects the full 60-minute file with HTTP 400** ("corrupted or unsupported") even though a 5-minute slice of the same file works. So it's a **duration/size ceiling**, not an encoding fault. On the full file the code correctly falls back to whisper-1 — meaning today it completes but **without** speaker labels, so the attendee-count bug still shows on full meetings.

**Fix is a short, well-defined spike** (already scripted for the build model): test re-mux vs. client-side chunking on the full file, implement whichever passes, and gate on the **full 60-min real file** (not a clip). Details and exact commands are in the build script.

## 5. Where everything lives
- **Build script (driftproof, for the build model):** `build-specs/BUILD-AUDIO-DIARIZE-001.md`
- **Functional test (real 60-min file):** `build-specs/functional_test_diarize.py`
- **Code + tests:** branch `feat/audio-diarize-001` @ `544028c`
- Repo: `/home/clawdbot/audio-compiler`

## 6. Cost note
All on your existing OpenAI key (no new service). Diarize is usage-billed and slower (~0.4× realtime; a 60-min file ≈ several minutes), which is fine for the async email flow. Recommend confirming per-minute price before high volume.

## 7. Rollback (already wired)
`USE_DIARIZATION=false` in `.env` + `sudo systemctl restart audio-compiler.service` → instant revert to today's behavior, zero code change.
