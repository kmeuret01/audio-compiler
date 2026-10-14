"""Three customer deliverables for a compiled meeting.

1. Printable meeting notes PDF
2. Simple full-transcript PDF
3. Agent-ready markdown that contains the same notes plus the full transcript

GoAI Labs brand (goailabs.ai) is applied to the PDFs via app.services.brand.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

NOTES_PDF_SUFFIX = " Meeting Notes.pdf"
TRANSCRIPT_PDF_SUFFIX = " Transcript.pdf"
AGENT_MD_SUFFIX = " Agent Ready Markdown.md"

_SPEAKER_CHUNK = re.compile(r"^(speaker\s+)?\d+-[A-Za-z@?]$", re.IGNORECASE)
_FILENAME_DATE = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")
_STATED_DATE_FORMATS = (
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%m/%d/%Y",
    "%m/%d/%y",
)


def safe_title(title: str) -> str:
    """Filesystem-safe meeting name. Empty input becomes 'Meeting'."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or "Meeting")[:140]


def recording_date(source_name: str, stated: str = "") -> tuple[str, str, str]:
    """Return (iso_date, display, note).

    A real date stated in the meeting wins. Otherwise the date embedded in the
    audio filename is the recording date. Missing both yields today's date
    labeled as the compile date.
    """
    parsed = _parse_stated_date(stated or "")
    if parsed:
        return parsed.strftime("%Y-%m-%d"), _display_date(parsed), "stated in the meeting"
    match = _FILENAME_DATE.search(source_name or "")
    if match:
        parsed = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return parsed.strftime("%Y-%m-%d"), _display_date(parsed), "recording date"
    today = datetime.now()
    return today.strftime("%Y-%m-%d"), _display_date(today), "compile date"


def format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return ""
    minutes = int(round(float(seconds) / 60))
    if minutes < 1:
        return f"{int(seconds)}s"
    return f"{minutes}m"


def is_present_person(name: str) -> bool:
    """True for a person who belongs on the attendee line."""
    raw = (name or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    if lower in {"unknown", "speaker", "n/a", "none"}:
        return False
    if any(token in lower for token in ("discussed", "mentioned", "not present")):
        return False
    head = raw.split("(")[0].strip()
    if _SPEAKER_CHUNK.match(head):
        return False
    return True


def _discussed_names(attendees) -> list[str]:
    names = []
    for raw in attendees or []:
        text = str(raw)
        if any(token in text.lower() for token in ("discussed", "mentioned", "not present")):
            head = re.sub(r"\s*\(.*$", "", text).strip()
            if head:
                names.append(head.lower())
    return names


def _name_blocked(name: str, blocked: list[str]) -> bool:
    person = name.strip().lower()
    for other in blocked:
        if person == other or person.startswith(other + " ") or other.startswith(person + " "):
            return True
    return False


def display_speaker(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw or raw == "?":
        return "Speaker"
    if raw.lower().startswith("speaker "):
        return raw
    if re.match(r"^\d+-[A-Za-z@?]$", raw):
        return f"Speaker {raw}"
    return raw


def deliverable_stem(title: str, iso_date: str) -> str:
    return f"{safe_title(title)} - {iso_date}"


def cues_from_segments(segments: list) -> list[dict]:
    cues = []
    for seg in segments or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        cues.append({
            "start": _seconds_clock(float(seg.get("start") or 0)),
            "speaker": display_speaker(str(seg.get("speaker") or "")),
            "text": text,
        })
    return merge_cues(cues)


def cues_from_srt(raw: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", (raw or "").strip()):
        lines = [line.strip("\r") for line in block.splitlines() if line.strip()]
        time_at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_at is None:
            continue
        start = lines[time_at].split("-->", 1)[0].strip()
        text = " ".join(lines[time_at + 1:]).strip()
        if not text:
            continue
        speaker = ""
        match = re.match(r"^([^:]{1,40}):\s+(.*)$", text)
        if match and not match.group(1).lower().startswith("http"):
            speaker, text = match.group(1).strip(), match.group(2).strip()
        if not text:
            continue
        cues.append({
            "start": _srt_clock(start),
            "speaker": display_speaker(speaker),
            "text": text,
        })
    return merge_cues(cues)


def merge_cues(cues: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for cue in cues:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        if merged and merged[-1]["speaker"] == cue.get("speaker"):
            merged[-1]["text"] = f"{merged[-1]['text']} {text}".strip()
        else:
            merged.append({
                "start": cue.get("start") or "00:00:00",
                "speaker": cue.get("speaker") or "Speaker",
                "text": text,
            })
    return merged


def parse_report_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def assemble_report(
    extracted: dict,
    metadata: dict,
    source_filename: str,
    duration_seconds: Optional[float],
    summary: str = "",
    action_items: str = "",
) -> dict:
    """One record the three files render from. Date and title prefer job data."""
    metadata = metadata or {}
    extracted = extracted or {}
    meta_title = (metadata.get("title") or "").strip()
    if not meta_title or meta_title.lower() == "unknown":
        meta_title = (extracted.get("title") or "").strip()
    title = safe_title(meta_title)

    iso_date, display, date_note = recording_date(source_filename, str(metadata.get("date") or ""))
    blocked = _discussed_names(metadata.get("attendees"))
    present = [
        n.strip() for n in (extracted.get("present") or [])
        if is_present_person(str(n)) and not _name_blocked(str(n), blocked)
    ]
    if not present:
        present = [
            n.strip() for n in (metadata.get("attendees") or [])
            if is_present_person(str(n)) and not _name_blocked(str(n), blocked)
        ]

    bluf = _clean_text(extracted.get("bluf") or "")
    if not bluf:
        bluf = _bluf_from_summary(summary)

    decisions = _clean_decisions(extracted.get("decisions"))
    actions = _clean_actions(extracted.get("actions"))
    if not actions:
        actions = _actions_from_json(action_items)
    questions = [_clean_text(q) for q in (extracted.get("open_questions") or []) if _clean_text(q)]
    risks = [_clean_text(r) for r in (extracted.get("risks") or []) if _clean_text(r)]

    return {
        "title": title,
        "date_iso": iso_date,
        "date_display": display,
        "date_note": date_note,
        "duration": format_duration(duration_seconds),
        "present": present,
        "bluf": bluf or "No bottom line could be drawn from this recording.",
        "decisions": decisions,
        "actions": actions,
        "open_questions": questions,
        "risks": risks,
    }


def write_deliverables(
    output_dir: str | Path,
    report: dict,
    cues: list[dict],
    job_id: str,
) -> dict:
    """Write the three customer files. Returns their paths."""
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stem = deliverable_stem(report["title"], report["date_iso"])
    notes_path = folder / f"{stem}{NOTES_PDF_SUFFIX}"
    transcript_path = folder / f"{stem}{TRANSCRIPT_PDF_SUFFIX}"
    agent_path = folder / f"{stem}{AGENT_MD_SUFFIX}"

    write_meeting_notes_pdf(notes_path, report)
    write_transcript_pdf(transcript_path, report, cues)
    agent_path.write_text(render_agent_markdown(report, cues, job_id), encoding="utf-8")
    (folder / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "meeting_notes_pdf": str(notes_path),
        "transcript_pdf": str(transcript_path),
        "agent_ready_markdown": str(agent_path),
    }


def list_deliverable_files(output_dir: Path) -> list[Path]:
    """The three files that get sent, when this folder has the new pack."""
    found = []
    if not output_dir or not output_dir.exists():
        return found
    for path in sorted(output_dir.iterdir()):
        name = path.name
        if name.endswith(NOTES_PDF_SUFFIX) or name.endswith(TRANSCRIPT_PDF_SUFFIX) or name.endswith(AGENT_MD_SUFFIX):
            found.append(path)
    return found


def render_agent_markdown(report: dict, cues: list[dict], job_id: str) -> str:
    lines = ["---", "type: meeting", f"title: {_yaml_quote(report['title'])}"]
    lines.append(f"date: {report['date_iso']}")
    if report.get("duration"):
        lines.append(f"duration: {_yaml_quote(report['duration'])}")
    lines.append(f"date_note: {_yaml_quote(report['date_note'])}")
    lines.append("producer: goailabs.ai")
    lines.append(f"source_job: {_yaml_quote(job_id)}")
    if report["present"]:
        lines.append("present:")
        for name in report["present"]:
            lines.append(f"  - {_yaml_quote(name)}")
    else:
        lines.append("present: []")
    if report["decisions"]:
        lines.append("decisions:")
        for decision in report["decisions"]:
            lines.append(f"  - text: {_yaml_quote(decision['text'])}")
            if decision.get("why"):
                lines.append(f"    why: {_yaml_quote(decision['why'])}")
    else:
        lines.append("decisions: []")
    if report["actions"]:
        lines.append("action_items:")
        for action in report["actions"]:
            lines.append(f"  - owner: {_yaml_quote(action.get('owner') or '')}")
            lines.append(f"    task: {_yaml_quote(action['task'])}")
            lines.append(f"    due: {_yaml_quote(action.get('due') or '')}")
            lines.append(f"    priority: {action.get('priority') or 'medium'}")
            lines.append("    status: open")
    else:
        lines.append("action_items: []")
    if report["open_questions"]:
        lines.append("open_questions:")
        for question in report["open_questions"]:
            lines.append(f"  - {_yaml_quote(question)}")
    else:
        lines.append("open_questions: []")
    lines.append("---")
    lines.append("")
    lines.append(f"# {report['title']}")
    lines.append("")
    lines.append("Go AI Labs · goailabs.ai · Confidential")
    lines.append("")
    lines.append(f"**Date:** {report['date_display']} ({report['date_note']})")
    if report.get("duration"):
        lines.append(f"**Duration:** {report['duration']}")
    present = ", ".join(report["present"]) if report["present"] else "Not named on the recording"
    lines.append(f"**Present:** {present}")
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(report["bluf"])
    lines.append("")
    lines.append("## Decisions")
    lines.append("")
    if report["decisions"]:
        for index, decision in enumerate(report["decisions"], start=1):
            lines.append(f"{index}. {decision['text']}")
            if decision.get("why"):
                lines.append(f"   Why: {decision['why']}")
            lines.append("")
    else:
        lines.append("No decision was settled in this recording.")
        lines.append("")
    lines.append("## Actions")
    lines.append("")
    if report["actions"]:
        for action in report["actions"]:
            owner = action.get("owner") or "Unassigned"
            due = action.get("due") or "no date stated"
            lines.append(f"- [ ] {owner} — {action['task']} — {due}")
        lines.append("")
    else:
        lines.append("No commitment was stated.")
        lines.append("")
    lines.append("## Open questions")
    lines.append("")
    if report["open_questions"]:
        for question in report["open_questions"]:
            lines.append(f"- {question}")
        lines.append("")
    else:
        lines.append("None stated.")
        lines.append("")
    if report["risks"]:
        lines.append("## Risks")
        lines.append("")
        for risk in report["risks"]:
            lines.append(f"- {risk}")
        lines.append("")
    lines.append("## Transcript")
    lines.append("")
    if not cues:
        lines.append("No transcript cues were available.")
        lines.append("")
    for cue in cues:
        lines.append(f"### {cue['start']} — {cue['speaker']}")
        lines.append("")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_meeting_notes_pdf(path: Path, report: dict) -> None:
    from reportlab.platypus import Paragraph, Spacer

    styles = _pdf_styles()
    story = _title_block(report, styles, "Meeting notes")
    story.append(Paragraph("BOTTOM LINE", styles["SectionHead"]))
    story.append(Paragraph(escape(report["bluf"]), styles["Body"]))
    story.append(Paragraph("DECISIONS", styles["SectionHead"]))
    if report["decisions"]:
        for decision in report["decisions"]:
            story.append(Paragraph(escape(decision["text"]), styles["NoteBullet"]))
            if decision.get("why"):
                story.append(Paragraph(escape(decision["why"]), styles["NoteWhy"]))
    else:
        story.append(Paragraph("No decision was settled in this recording.", styles["Body"]))
    story.append(Paragraph("ACTIONS", styles["SectionHead"]))
    if report["actions"]:
        for action in report["actions"]:
            owner = action.get("owner") or "Unassigned"
            due = action.get("due") or "no date stated"
            line = f"{owner} — {action['task']} — {due}"
            story.append(Paragraph(escape(line), styles["NoteBullet"]))
    else:
        story.append(Paragraph("No commitment was stated.", styles["Body"]))
    story.append(Paragraph("OPEN QUESTIONS", styles["SectionHead"]))
    if report["open_questions"]:
        for question in report["open_questions"]:
            story.append(Paragraph(escape(question), styles["NoteBullet"]))
    else:
        story.append(Paragraph("None stated.", styles["Body"]))
    if report["risks"]:
        story.append(Paragraph("RISKS", styles["SectionHead"]))
        for risk in report["risks"]:
            story.append(Paragraph(escape(risk), styles["NoteBullet"]))
    story.append(Spacer(1, 8))
    _build_pdf(path, story, "MEETING NOTES")


def write_transcript_pdf(path: Path, report: dict, cues: list[dict]) -> None:
    from reportlab.platypus import Paragraph

    styles = _pdf_styles()
    story = _title_block(report, styles, "Transcript")
    if not cues:
        story.append(Paragraph("No transcript cues were available.", styles["Body"]))
    for cue in cues:
        label = f"{cue['start']}   {cue['speaker']}"
        story.append(Paragraph(escape(label), styles["CueLabel"]))
        story.append(Paragraph(escape(cue["text"]), styles["Body"]))
    _build_pdf(path, story, "TRANSCRIPT")


REPORT_SYSTEM = """You extract a meeting record from a transcript. Return ONLY valid JSON with these keys:
  "title": string — concise meeting name from the content. Never use a filename.
  "present": array of strings — only people who are in the room. Include someone when another speaker addresses them by name, or when a voice is identified ("that was Kevin"). Exclude mentors, past clients, coaches, investors, and anyone who appears only inside a story. Exclude labels like "Speaker 1-A". If nobody was named as present, return [].
  "bluf": string — 2 or 3 complete sentences. Include the specific offer, counts, prices, and the question the room was asked. A sentence that only says "strategies" or "challenges" without those specifics is not acceptable. No bullet characters. No leading dash.
  "decisions": array of {"text": string, "why": string}. A decision is something the room settled. A plan the speaker is already running is not a decision unless the room agreed to it. text is one full sentence. why is one sentence, or "" when no reason was given.
  "actions": array of {"owner": string or null, "task": string, "due": string or null, "priority": "high" | "medium" | "low"}. Only a commitment a person made ("I will", "you take"). owner and due stay null when the recording did not say them. Never invent a name or a date. Do not turn goals or ideas into actions.
  "open_questions": array of strings — questions the room left unresolved, including the question the speaker asked the group to think about.
  "risks": array of strings — only risks someone raised. Otherwise [].

Do not invent facts. Do not use speaker-chunk labels as people's names."""


def report_user_content(transcript: str) -> str:
    text = transcript or ""
    if len(text) > 90000:
        text = text[:90000] + "\n\n[transcript truncated]"
    return f"Transcript:\n\n{text}"


def _title_block(report: dict, styles, kind: str):
    from reportlab.platypus import Paragraph, Spacer

    meta_bits = [report["date_display"], report["date_note"]]
    if report.get("duration"):
        meta_bits.append(report["duration"])
    present = ", ".join(report["present"]) if report["present"] else "Not named on the recording"
    return [
        Paragraph(escape(report["title"]), styles["DocTitle"]),
        Paragraph(escape(kind), styles["Kind"]),
        Paragraph("goailabs.ai", styles["BrandLine"]),
        Paragraph(escape(" · ".join(meta_bits)), styles["Meta"]),
        Paragraph(escape(f"Present: {present}"), styles["Meta"]),
        Spacer(1, 6),
    ]


def _build_pdf(path: Path, story, doc_type: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

    from app.services.brand import draw_header_footer

    def _page(canvas, doc):
        draw_header_footer(canvas, doc, doc_type)

    doc = BaseDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.95 * inch,
        bottomMargin=0.75 * inch,
        title=path.stem,
        author="Go AI Labs",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_page)])
    doc.build(story)


def _pdf_styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT

    from app.services.brand import ACCENT, BLACK, DARK_GRAY, MID_GRAY, FONT_BODY, FONT_HEADING, FONT_MONO, FONT_MONO_BOLD

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="DocTitle", fontName=FONT_HEADING, fontSize=16, leading=20,
        textColor=BLACK, spaceAfter=2, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="Kind", fontName=FONT_MONO, fontSize=8, leading=11,
        textColor=ACCENT, spaceAfter=1,
    ))
    styles.add(ParagraphStyle(
        name="BrandLine", fontName=FONT_MONO, fontSize=8, leading=11,
        textColor=MID_GRAY, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Meta", fontName=FONT_BODY, fontSize=9, leading=12,
        textColor=DARK_GRAY, spaceAfter=1,
    ))
    styles.add(ParagraphStyle(
        name="SectionHead", fontName=FONT_MONO_BOLD, fontSize=8.5, leading=12,
        textColor=ACCENT, spaceBefore=12, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Body", fontName=FONT_BODY, fontSize=10, leading=14,
        textColor=DARK_GRAY, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="NoteBullet", fontName=FONT_BODY, fontSize=10, leading=13,
        textColor=DARK_GRAY, leftIndent=10, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="NoteWhy", fontName=FONT_BODY, fontSize=9, leading=12,
        textColor=MID_GRAY, leftIndent=18, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="CueLabel", fontName=FONT_MONO_BOLD, fontSize=8, leading=11,
        textColor=ACCENT, spaceBefore=8, spaceAfter=1,
    ))
    return styles


def _parse_stated_date(stated: str):
    text = (stated or "").strip()
    if not text or text.lower() == "unknown":
        return None
    for fmt in _STATED_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _display_date(value: datetime) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _seconds_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _srt_clock(raw: str) -> str:
    head = raw.split(",")[0].strip()
    parts = head.split(":")
    if len(parts) != 3:
        return "00:00:00"
    try:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    except ValueError:
        return "00:00:00"


def _clean_text(value) -> str:
    text = str(value or "")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip(" -\t")
    return text


def _clean_decisions(raw) -> list[dict]:
    cleaned = []
    for item in raw or []:
        if isinstance(item, str):
            text = _clean_text(item)
            why = ""
        elif isinstance(item, dict):
            text = _clean_text(item.get("text") or item.get("decision"))
            why = _clean_text(item.get("why") or item.get("rationale"))
        else:
            continue
        if text:
            cleaned.append({"text": text, "why": why})
    return cleaned


def _clean_actions(raw) -> list[dict]:
    cleaned = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        task = _clean_text(item.get("task") or item.get("action"))
        if not task:
            continue
        owner = _clean_text(item.get("owner") or item.get("assignee") or "")
        owner = re.sub(r"\s*\([^)]*\)\s*$", "", owner).strip()
        if owner.lower() in {"null", "none", "unassigned", "unknown", ""} or _SPEAKER_CHUNK.match(owner):
            owner = ""
        due = _clean_text(item.get("due") or item.get("deadline") or "")
        if due.lower() in {"null", "none", "unknown"}:
            due = ""
        priority = str(item.get("priority") or "medium").lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        cleaned.append({"owner": owner, "task": task, "due": due, "priority": priority})
    return cleaned


def _actions_from_json(raw: str) -> list[dict]:
    try:
        data = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("action_items") or data.get("actions") or []
    return _clean_actions(data if isinstance(data, list) else [])


def _bluf_from_summary(summary: str) -> str:
    text = (summary or "").strip()
    if not text:
        return ""
    purpose = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.endswith(":") or stripped.lower().startswith("purpose"):
            if stripped.lower().startswith("purpose"):
                continue
            if purpose:
                break
            continue
        if stripped.startswith("- "):
            break
        purpose = stripped
        break
    return _clean_text(purpose)


def _yaml_quote(value: str) -> str:
    text = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'
