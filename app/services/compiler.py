"""Audio compiler — the full 7-step pipeline.

Preserves every LLM prompt verbatim from the original audio_processor.py.
Each step is traced via run_stage().
"""

import json
import time
from pathlib import Path
from typing import Optional

import httpx

from app.config import Settings
from app.database import Database
from app.tracing import run_stage
from app.services.transcription import transcribe
from app.services.pdf_generator import (
    generate_meeting_notes_pdf,
    generate_action_items_pdf,
    generate_transcript_pdf,
)


# ── LLM Caller ──────────────────────────────────────────────────────

async def _call_openai(
    system: str,
    user_content: str,
    settings: Settings,
    max_tokens: int = 2000,
) -> dict:
    """Call OpenAI chat completion. Returns {"text": str, "usage": dict}."""
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": max_tokens,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    return {
        "text": data["choices"][0]["message"]["content"].strip(),
        "usage": data.get("usage", {}),
    }


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences from LLM output."""
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        return "\n".join(lines)
    return raw


# ── Pipeline Stages ──────────────────────────────────────────────────

async def _stage_1_transcribe(audio_path: str, settings: Settings) -> dict:
    """Stage 1: Whisper transcription."""
    result = await transcribe(audio_path, settings)
    if not result["success"]:
        raise RuntimeError(f"Transcription failed: {result['error']}")
    return result


async def _stage_2_metadata(transcript: str, settings: Settings) -> dict:
    """Stage 2: Extract meeting metadata (date, time, attendees)."""
    system = (
        "You extract meeting metadata from transcripts. Return ONLY valid JSON with these keys:\n"
        '  "date": string (e.g. "December 5, 2018") or "Unknown",\n'
        '  "time": string (e.g. "2:00 PM") or "Unknown",\n'
        '  "attendees": array of strings with names of people mentioned or identifiable.\n'
        "Infer the date and attendees from context clues in the transcript. "
        "If a name is mentioned as the subject of discussion (not present), note them as "
        '"[Name] (discussed, not present)". List the speaker/narrator if identifiable.'
    )
    result = await _call_openai(system, f"Transcript:\n\n{transcript}", settings)
    raw = _strip_code_fences(result["text"])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"date": "Unknown", "time": "Unknown", "attendees": []}
    parsed["usage"] = result["usage"]
    return parsed


async def _stage_3_notes(transcript: str, settings: Settings) -> dict:
    """Stage 3: Generate meeting notes (topic-by-topic)."""
    system = """You are a professional meeting note-taker. Given a transcript, produce detailed, well-structured meeting notes in a TOPIC-BY-TOPIC format.

FORMAT REQUIREMENTS:
1. Organize notes by TOPIC - each major discussion point gets its own section
2. Each topic section must have:
   - A "Topic Title:" line with a descriptive title
   - 2-4 paragraphs of detailed content explaining what was discussed
   - A "Conclusion:" line summarizing the key takeaway for that topic

3. After all topics, include:
   - "Next Arrangements" section with action items as checkbox-style "[ ]" items
   - "Recommendations" section with bullet points for follow-up considerations

EXAMPLE FORMAT:
Topic Title: Working Style and Communication Norms

The participant discussed their preferred communication style and how they handle stakeholder relationships. They noted uncertainty about proper etiquette for CC'ing others on emails.

Discussion covered personality assessment results showing high D and C traits. The participant gains energy from group brainstorming rather than one-on-one meetings.

Conclusion: Clarify stakeholder communication etiquette; align work with natural strengths while adding structure.

Topic Title: Project Prioritization

[Next topic content...]

Conclusion: [Topic conclusion]

Next Arrangements

[ ] First action item with specific details
[ ] Second action item
[ ] Third action item

Recommendations

- First consideration based on the discussion
- Second consideration for follow-up
- Third point worth noting

IMPORTANT:
- Do NOT use markdown syntax (no #, ##, **, etc.)
- Do NOT use bullet points for topic content - use full paragraphs
- Each topic MUST have a Conclusion line
- Be detailed and thorough - capture the substance of discussions
- Typically identify 6-12 distinct topics from a meeting"""

    result = await _call_openai(system, f"Transcript:\n\n{transcript}", settings, max_tokens=4000)
    return {"text": result["text"], "usage": result["usage"]}


async def _stage_4_actions(transcript: str, settings: Settings) -> dict:
    """Stage 4: Extract action items."""
    system = (
        "You are a project manager. Given a meeting transcript, extract all action items. "
        "Return ONLY valid JSON: an array of objects with keys: "
        '"task" (string), "assignee" (string or null), "deadline" (string or null), "priority" (high/medium/low).'
    )
    result = await _call_openai(system, f"Transcript:\n\n{transcript}", settings)
    raw = _strip_code_fences(result["text"])
    try:
        parsed = json.loads(raw)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        formatted = raw
    return {"text": formatted, "usage": result["usage"]}


async def _stage_5_summary(transcript: str, settings: Settings) -> dict:
    """Stage 5: Generate executive summary."""
    system = (
        "You are an executive assistant. Given a meeting transcript, produce a concise executive "
        "summary. Do NOT use markdown heading syntax (no # or ## characters). "
        "Format section headers as bold-style plain text ending with a colon, e.g. 'Purpose of the Meeting:' "
        "Put each section header on its own line, then leave a blank line before the paragraph text. "
        "Leave an extra blank line between the end of one section's content and the next section header. "
        "For the 'Next Steps:' section, list each step on its own line prefixed with '- '. "
        "Include: Purpose of the Meeting, Key Outcomes, and Next Steps. "
        "Keep it under 300 words."
    )
    result = await _call_openai(system, f"Transcript:\n\n{transcript}", settings)
    return {"text": result["text"], "usage": result["usage"]}


async def _stage_6_review(notes: str, action_items: str, settings: Settings) -> dict:
    """Stage 6: AI quality review."""
    system = """You are a meeting documentation quality reviewer. Review the provided meeting notes and action items against best practices.

Evaluate against these criteria:
1. CLARITY: Are the notes clear and easy to understand?
2. COMPLETENESS: Do the notes capture key discussion points, decisions, and outcomes?
3. ACTION ITEMS: Are action items specific, measurable, and assigned with deadlines?
4. STRUCTURE: Is the information well-organized and logically structured?
5. ACTIONABILITY: Can someone who wasn't in the meeting understand what happened and what needs to be done?

Provide brief, constructive feedback in this format:

STRENGTHS:
- [2-3 bullet points of what was done well]

AREAS FOR IMPROVEMENT:
- [2-3 specific suggestions if any]

OVERALL QUALITY: [Excellent/Good/Needs Improvement]

Keep feedback concise and actionable. Focus on the most important points."""

    user_content = f"""MEETING NOTES:
{notes}

ACTION ITEMS:
{action_items}

Please review these against meeting documentation best practices."""

    result = await _call_openai(system, user_content, settings, max_tokens=500)
    return {"text": result["text"], "usage": result["usage"]}


async def _stage_7_pdfs(
    output_dir: Path,
    filename: str,
    notes: str,
    action_items: str,
    transcript: str,
    metadata: dict,
) -> dict:
    """Stage 7: Generate branded PDFs."""
    notes_pdf = output_dir / "meeting_notes.pdf"
    generate_meeting_notes_pdf(notes, filename, notes_pdf, metadata)

    items_pdf = output_dir / "action_items.pdf"
    generate_action_items_pdf(action_items, filename, items_pdf, metadata)

    transcript_pdf = output_dir / "transcript.pdf"
    generate_transcript_pdf(transcript, filename, transcript_pdf, metadata)

    return {
        "meeting_notes_pdf": str(notes_pdf),
        "action_items_pdf": str(items_pdf),
        "transcript_pdf": str(transcript_pdf),
    }


# ── Main Pipeline ────────────────────────────────────────────────────

async def compile_audio(
    job_id: str,
    audio_path: str,
    db: Database,
    settings: Settings,
    overrides: Optional[dict] = None,
) -> dict:
    """Run the full 7-step audio compilation pipeline with tracing."""
    overrides = overrides or {}
    start = time.monotonic()
    filename = Path(audio_path).name
    output_dir = Path(settings.output_dir) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1: Transcription
    if "transcript" in overrides:
        db.skip_stage(job_id, "stage_1_transcription", "pre-computed by caller")
        transcription = {"transcript": overrides["transcript"], "duration_seconds": 0, "word_count": len(overrides["transcript"].split())}
    else:
        transcription = await run_stage(
            job_id, "stage_1_transcription", db, _stage_1_transcribe,
            audio_path, settings,
            input_summary=f"Audio file: {filename}",
            llm_model="whisper-1",
        )

    transcript = transcription["transcript"]
    transcript_path = output_dir / "transcript.txt"
    transcript_path.write_text(transcript, encoding="utf-8")

    # Stage 2: Metadata
    if "metadata" in overrides:
        db.skip_stage(job_id, "stage_2_metadata", "pre-computed by caller")
        metadata = overrides["metadata"]
    else:
        metadata = await run_stage(
            job_id, "stage_2_metadata", db, _stage_2_metadata,
            transcript, settings,
            input_summary=f"Transcript: {len(transcript.split())} words",
            llm_model=settings.llm_model,
        )

    metadata_clean = {k: v for k, v in metadata.items() if k != "usage"}
    (output_dir / "metadata.json").write_text(json.dumps(metadata_clean, indent=2), encoding="utf-8")

    # Stage 3: Meeting notes
    if "notes" in overrides:
        db.skip_stage(job_id, "stage_3_notes", "pre-computed by caller")
        notes = overrides["notes"]
    else:
        notes_result = await run_stage(
            job_id, "stage_3_notes", db, _stage_3_notes,
            transcript, settings,
            input_summary=f"Transcript: {len(transcript.split())} words",
            llm_model=settings.llm_model,
        )
        notes = notes_result["text"]

    notes_path = output_dir / "meeting_notes.md"
    notes_path.write_text(notes, encoding="utf-8")

    # Stage 4: Action items
    if "action_items" in overrides:
        db.skip_stage(job_id, "stage_4_actions", "pre-computed by caller")
        action_items = overrides["action_items"]
    else:
        actions_result = await run_stage(
            job_id, "stage_4_actions", db, _stage_4_actions,
            transcript, settings,
            input_summary=f"Transcript: {len(transcript.split())} words",
            llm_model=settings.llm_model,
        )
        action_items = actions_result["text"]

    items_path = output_dir / "action_items.json"
    items_path.write_text(action_items, encoding="utf-8")

    # Stage 5: Summary
    if "summary" in overrides:
        db.skip_stage(job_id, "stage_5_summary", "pre-computed by caller")
        summary = overrides["summary"]
    else:
        summary_result = await run_stage(
            job_id, "stage_5_summary", db, _stage_5_summary,
            transcript, settings,
            input_summary=f"Transcript: {len(transcript.split())} words",
            llm_model=settings.llm_model,
        )
        summary = summary_result["text"]

    summary_path = output_dir / "summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    # Stage 6: Quality review
    review_result = await run_stage(
        job_id, "stage_6_review", db, _stage_6_review,
        notes, action_items, settings,
        input_summary=f"Notes: {len(notes.split())} words, Actions: {len(action_items.split())} words",
        llm_model=settings.llm_model,
    )
    review = review_result["text"]
    review_path = output_dir / "quality_review.json"
    review_path.write_text(json.dumps({"review": review}, indent=2), encoding="utf-8")

    # Stage 7: PDFs
    pdf_result = await run_stage(
        job_id, "stage_7_pdf", db, _stage_7_pdfs,
        output_dir, filename, notes, action_items, transcript, metadata_clean,
        input_summary="Generating 3 branded PDFs",
    )

    total_ms = int((time.monotonic() - start) * 1000)
    db.complete_job(
        job_id,
        total_duration_ms=total_ms,
        output_dir=str(output_dir),
        audio_duration=transcription.get("duration_seconds", 0),
    )

    return {
        "job_id": job_id,
        "status": "completed",
        "total_duration_ms": total_ms,
        "output_dir": str(output_dir),
        "outputs": {
            "transcript": str(transcript_path),
            "metadata": str(output_dir / "metadata.json"),
            "meeting_notes": str(notes_path),
            "action_items": str(items_path),
            "summary": str(summary_path),
            "quality_review": str(review_path),
            "meeting_notes_pdf": pdf_result["meeting_notes_pdf"],
            "action_items_pdf": pdf_result["action_items_pdf"],
            "transcript_pdf": pdf_result["transcript_pdf"],
        },
        "summary_text": summary,
        "metadata": metadata_clean,
    }
