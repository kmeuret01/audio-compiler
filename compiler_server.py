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
from app.services.output_generator import generate_all_outputs


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
    system = """You are an elite executive meeting analyst. Given a transcript, produce detailed, substantive meeting notes organized by topic.

You must capture SPECIFICS — names, numbers, dollar amounts, tool names, strategies, exact quotes that reveal intent. Generic summaries are unacceptable.

FORMAT REQUIREMENTS:
1. Organize by TOPIC — each major discussion point gets its own section
2. Each topic section must have:
   - A "Topic Title:" line with a specific, descriptive title (NOT generic like "Project Overview")
   - 2-4 paragraphs capturing the SUBSTANCE of what was discussed — specific tools, strategies, numbers, reasoning, disagreements, and decisions
   - A "Conclusion:" line with the specific decision or takeaway (not a restatement of the topic)

3. After all topics, include:
   - "Next Arrangements" section with specific action items as "[ ]" checkbox items, each with WHO is responsible
   - "Recommendations" section with strategic observations the participants should consider

QUALITY STANDARDS:
- If someone mentioned a specific tool, company, dollar amount, or metric — it MUST appear in the notes
- If a decision was made with reasoning — capture BOTH the decision AND the reasoning
- If there was disagreement or a pivot in thinking — capture that dynamic
- Conclusions must be SPECIFIC DECISIONS, not vague restatements like "Continue to explore options"
- Action items must name the responsible person when discussed

BAD EXAMPLE (too generic):
Topic Title: Marketing Strategy
The team discussed various marketing approaches and decided to focus on what's working.
Conclusion: Continue to refine marketing strategies based on data.

GOOD EXAMPLE (specific and substantive):
Topic Title: Forum Seeding Strategy — VA-Driven with Anti-Detection Guardrails
Kevin and Jacob discussed using VAs rather than automation for forum posting on Reddit and Quora. Jacob explained that forums detect and ban automated posting, making human operators essential. The strategy involves creating 10+ accounts — some asking questions, some answering — to control the narrative. Jacob emphasized accounts must be "warmed up" on iOS devices for higher trust scores. Kevin framed the non-automatable nature as a competitive moat: "If people won't invest in putting a human on it, that's our advantage."
Conclusion: Jacob will develop the forum posting framework and hire a VA. Automation limited to account warm-up only; all posting must be human-operated to avoid detection and bans.

IMPORTANT:
- Do NOT use markdown syntax (no #, ##, **, etc.)
- Do NOT use bullet points for topic content — use full paragraphs
- Each topic MUST have a Conclusion line with a SPECIFIC decision
- Typically identify 6-12 distinct topics from a meeting
- Capture the speakers' own language and frameworks when they use distinctive terms"""

    result = await _call_openai(system, f"Transcript:\n\n{transcript}", settings, max_tokens=4000)
    return {"text": result["text"], "usage": result["usage"]}


async def _stage_4_actions(transcript: str, settings: Settings) -> dict:
    """Stage 4: Extract action items."""
    system = """You are a project manager extracting action items from a meeting transcript.

Return ONLY valid JSON: an array of objects with these keys:
- "task" (string) — SPECIFIC description of what needs to be done. Include tool names, targets, and scope. Bad: "Follow up on marketing." Good: "Contact Wix autoblogger developer via Telegram to request custom blog content submission capability."
- "assignee" (string or null) — Person responsible. Use their actual name from the transcript. If unassigned, use null.
- "deadline" (string or null) — Any mentioned timeline. Use exact language from transcript like "within 7 days" or "before next meeting."
- "priority" (string) — "high" for items discussed as immediate/urgent/step-0, "medium" for follow-up items, "low" for backlog/future considerations.

CRITICAL RULES:
- Extract the speakers' OWN execution framework if they defined one (e.g., "Step 0 is personas, Step 1 is blog automation, Step 2 is forum posting")
- Preserve specific details: dollar amounts, tool names, platform names, account counts
- If someone said "I'll do X" — that person is the assignee
- Include spending authorizations and budget decisions as action items
- Do NOT genericize. "Set up forum posting" is bad. "Build forum posting framework: create 10+ warm accounts on Reddit/Quora using iOS devices, hire VA from Fiverr, develop posting playbook with question/answer account pairs" is good."""
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
    system = """You are an executive assistant producing a concise but SUBSTANTIVE executive summary.

Do NOT use markdown heading syntax (no # or ## characters).
Format section headers as plain text ending with a colon on their own line.
Leave a blank line between section header and content.
Leave an extra blank line between sections.

Required sections:

Purpose of the Meeting:
[2-3 sentences explaining WHY this meeting happened and what it aimed to accomplish. Be specific — name the project, the business, the challenge.]

Key Outcomes:
[4-6 bullet points using "- " prefix. Each outcome must be SPECIFIC — include names, numbers, tools, and decisions. Not "discussed marketing" but "decided to prioritize Facebook Ads over Google Ads due to unresolved tracking tag issue; Jacob to run targeted campaigns using scraped Instagram audience data."]

Next Steps:
[3-5 bullet points using "- " prefix. Each must name WHO does WHAT by WHEN if discussed.]

Spending & Resources:
[Only include if financial decisions were made. Note specific amounts, authorizations, and constraints.]

QUALITY STANDARD: A reader who was NOT in the meeting should be able to understand exactly what was decided and why. Generic summaries that could apply to any meeting are unacceptable.

Keep it under 400 words."""
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


async def _stage_7_outputs(
    output_dir: Path,
    filename: str,
    notes: str,
    action_items: str,
    transcript: str,
    summary: str,
    metadata: dict,
) -> dict:
    """Stage 7: Generate AI Labs branded outputs (PDFs, DOCX, email HTML)."""
    # Add source filename to metadata
    metadata_with_source = {**metadata, 'source_filename': filename}

    outputs = generate_all_outputs(
        job_id="",  # Not needed for output generation
        output_dir=str(output_dir),
        compilation_data={
            'transcript': transcript,
            'metadata': metadata_with_source,
            'meeting_notes': notes,
            'action_items': action_items,
            'executive_summary': summary,
        }
    )

    return {
        "executive_brief_pdf": outputs.get('executive_brief_pdf'),
        "full_debrief_docx": outputs.get('full_debrief_docx'),
        "transcript_pdf": outputs.get('transcript_pdf'),
        "email_body_html": outputs.get('email_body_html'),
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

    # Stage 7: AI Labs branded outputs (PDFs, DOCX, email HTML)
    output_result = await run_stage(
        job_id, "stage_7_outputs", db, _stage_7_outputs,
        output_dir, filename, notes, action_items, transcript, summary, metadata_clean,
        input_summary="Generating AI Labs branded outputs (3 files + email HTML)",
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
            "executive_brief_pdf": output_result.get("executive_brief_pdf"),
            "full_debrief_docx": output_result.get("full_debrief_docx"),
            "transcript_pdf": output_result.get("transcript_pdf"),
        },
        "summary_text": summary,
        "email_body_html": output_result.get("email_body_html"),
        "metadata": metadata_clean,
    }
