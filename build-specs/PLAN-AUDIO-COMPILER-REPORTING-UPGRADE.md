# Audio Compiler Reporting Upgrade

**Prepared for:** Kevin Meuret  
**Date:** 2026-08-04  
**Status:** Plan only — not approved for build yet  
**Cursor plan file:** `/home/clawdbot/.cursor/plans/Report Quality Upgrade-623ea9d8.plan.md`  
**This document:** `/home/clawdbot/audio-compiler/build-specs/PLAN-AUDIO-COMPILER-REPORTING-UPGRADE.md`

---

## Context

`main` for audio-compiler is pushed to origin at merge commit `25d6cfb` (FEAT-AUDIO-DIARIZE-001 landed). Quality review of the branded deliverables used the real 60-minute South County run:

`/tmp/diarize_ft_9t5xhyks/out/4d6f21a3-41b/`

Goal: bring Go AI Labs branded reports (email → executive brief PDF → full debrief DOCX) up to the 2026 competitive bar for **look and reading flow**, without rebuilding a full meeting-bot product.

---

## What we ship today (strengths)

- Clear brand system in `app/services/brand.py`: DM Sans + Space Mono, terracotta accent, confidential footer.
- Sensible artifact ladder: skim email → 1–2p executive brief PDF → editable full debrief DOCX → transcript/SRT + Notion/Confluence exports (`output_generator.py`).
- Email already aims at a 30-second scan (`template_email.py`).

---

## Where quality loses vs Fathom / Otter / Fireflies / Grain / Fellow

| Surface | Current failure | Competitor norm |
|---|---|---|
| Email meta | Lists discussed people (`Cohen, Kimberly… +11 more`); date/duration often `Unknown` | Present speakers only; date/time always filled |
| BLUF | Choppy join (`…strategies. - Initial setup…`) | 2–3 clean sentences, no list artifacts |
| Decisions / next steps | Truncated mid-thought; owners as `Speaker 1-E` | Named owners + due date chips |
| Notes body | Topic walls; “Speaker N-X” throughout | Real names; **Discussed / Decided / Next** per topic |
| Actions | Good task text, but assignee = chunk labels | Owner resolution + priority grouping |
| Navigation | No jump from summary → moment in transcript | Timestamped deep links / chapter TOC |
| Flow after open | Dense PDF/DOCX; no “read path” hierarchy | Fixed skim order: Summary → Decisions → Actions → Topics → Transcript |

### Patterns to steal (not full product clones)

- **Fathom** — best structured post-call pack: Summary, Key Points, Decisions *with why*, Actions with owners.
- **Otter** — meeting-type templates; consistent section schema.
- **Fireflies** — searchable Q&A over the meeting (later); strong action→CRM handoff.
- **Grain / tl;dv** — clip/share moments (only if we keep/store audio URLs).
- **Fellow** — agenda → notes → open-loop action tracking across meetings.

### Intended read path

```
Email (30s skim)
  → Executive Brief PDF
    → Full Debrief DOCX
      → Transcript PDF / SRT
```

---

## Recommended product bar

**Target:** Fathom-grade reading flow + AI Labs brand, delivered as the same email+PDF+DOCX pack.

**Out of scope for this plan:** live bots, CRM auto-write, video highlight reels, cross-meeting Ask-AI.

---

## Workstreams

### 1. Content integrity (unblocks every surface)

Root cause of the “cheap” feel is **speaker identity leakage** from chunked diarize (`Speaker 1-A`) into stages 2–5 and all templates.

- Add a **speaker resolution pass** after diarization (before labeled transcript is built): map chunk-local labels → stable display names (Kevin / Dave / Jacob) using diarize labels + optional `transcribe_prompt` name hints + metadata.
- Filter attendees for customer-facing outputs: **present only** (keep discussed-names in an internal appendix if needed).
- Fill date/duration: prefer email/job metadata, else ffprobe duration; never print raw `Unknown` in branded headers.

**Primary touchpoints:** `app/services/compiler.py` (stage-1→2 handoff), `app/services/transcription.py` (or a thin `speaker_resolve` helper). Prompt edits only if Gate -1 allows (today the five LLM prompts are frozen).

### 2. Canonical report schema (one model → all templates)

Define a single structured object every template consumes:

- `bluf` (2–3 sentences)
- `key_points[]` (3–7)
- `decisions[]` `{text, why, owners[]}`
- `actions[]` `{task, owner, due, priority}`
- `topics[]` `{title, discussed, decided, next[]}`
- `meta` `{title, date, duration, present[], discussed[]}`

Refactor extractors in `app/services/output_generator.py` (`extract_bluf`, `extract_decisions`, topic parsing) to stop regex-gluing list markers into BLUF.

### 3. Reading-flow redesign (look + hierarchy)

**Email** (`template_email.py`)

- Meta: present attendees only; show duration; drop “+N more” noise when N are discussed ghosts.
- Fixed order: BLUF → Key decisions (max 4, full short clauses) → Next steps as `Owner — task — due`.
- Optional one-line “Open loops” count.

**Executive Brief PDF** (`template_executive_brief.py`)

- Match Fathom skim: BLUF → Key points → Decisions (with why) → Execution board (owner | due | priority).
- Keep branded section heads; reduce body density.

**Full Debrief DOCX** (`template_debrief.py`)

- Enforce per-topic **Discussed / Decided / Next** blocks (template already assumes this; LLM notes today are prose walls).
- Execution board uses resolved names; strip chunk prefixes from body text.

**Transcript PDF** (`template_transcript.py`)

- Chapter TOC from topics with start timestamps; wire real names into speaker-prefixed cues.

### 4. Competitive extras (after core)

- Timestamp jump list in email/brief (`00:12:40 — BNDD sequencing`).
- Meeting-type presets (ops / sales / 1:1) — same schema, different section weights.
- Follow-up email draft block from `actions[]`.
- Later (separate feature): Ask-over-one-meeting Q&A.

### 5. Acceptance / quality gate

On the same 60-min South County file:

- Zero `Speaker N-X` in email, brief, debrief, summary.
- Present attendees ∈ [2,4]; discussed names not in email meta.
- BLUF has no leading `-` / joined list artifacts.
- Every high-priority action has a human owner + non-null due when said in audio.
- Email scannable ≤30s; brief ≤2 pages; debrief topics use Discussed/Decided/Next.

---

## Suggested sequencing

1. Speaker resolution + present-only meta (highest ROI).
2. Canonical schema + extractor cleanup.
3. Template flow pass (email → brief → debrief).
4. Timestamp chapters + meeting-type presets.
5. Gate -1 plan + adversarial reviews before coding (platform protocol).

---

## Non-goals

- Replacing brand colors/fonts (already distinctive).
- Building Grain-style video reels or Fireflies CRM sync in this pass.
- Editing the five frozen LLM prompts without an approved Gate -1 scope change.

---

## Plan locations (bookmark)

| Artifact | Path |
|---|---|
| Cursor plan (source of truth in IDE) | `/home/clawdbot/.cursor/plans/Report Quality Upgrade-623ea9d8.plan.md` |
| Reset / handoff markdown (this file) | `/home/clawdbot/audio-compiler/build-specs/PLAN-AUDIO-COMPILER-REPORTING-UPGRADE.md` |
| Sample branded run reviewed | `/tmp/diarize_ft_9t5xhyks/out/4d6f21a3-41b/` |
| Repo | `/home/clawdbot/audio-compiler` (`main` @ `25d6cfb`) |
